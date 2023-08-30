# Example searcher for Wallchain auction.

Searcher consists of:
- A listener that connects to auction by websocket,
  accepts incoming transactions, generates input data for a smart contract
  and sends it back to auction via websocket.
- A smart contract that will be called by wallchain contract with parameters
  provided by listener. This contract is inherited from special base contract.
  The `functon execute()` pays the bid by transferring `weth` to special address.
  Real searcher will perform arbitrage logic in this method.

## Running the code

To run this code, you'll need to pass following parameters to the script:

| Parameter name     | Description                                                                              |
|--------------------|------------------------------------------------------------------------------------------|
| --auction-url      | Base websocket url of the Wallchain auction. Should be something like ws://hostname      |
| --auction-token    | Authorization token for auction API                                                      |
| --capsule-address  | Address of Wallchain's capsule address, used to generate signatures                      |
| --contract-address | Address of searcher's contract                                                           |
| --private-key-hex  | PPrivate key for searcher contract owner address. Used to sign SearcherRequest structure |

For example:
```bash
./simple_searcher.py \
   --auction-url ws://domain-of-auction \
   --auction-token <my-token> \
   --contract-address 0x0000000000000000000000000000000000000000 \
   --capsule-address 0xB6bf0e1798c0A7cDC6caF3a6b64e43a2d3e3aC3E \
   --private-key-hex 0x0000000000000000000000000000000000000000000000000000000000000000
```

## How to adapt for you use-case

### Contract

Write you own smart contract extending `SearcherBase` contract. In `execute` function
add your logic for extracting MEV. Add code that will pay the bid as `WETH` to
`trustedExecutionCapsule` address. If your contract does not pay the bid, it will not pass
validation.

As your contract have to pay the price of gas it uses, you should make sure it has enough
native coin. You do not need to add any additional code here, as logic is in `SearcherBase`.

### Listener

If you plan to use python for listener, you can base your code on `simple_searcher.py`.
If you do not want to use/do not like default CLI interface, you can use
`AuctionClient` class and `sign_searcher_request`, `user_tx_hash` helper functions
directly.

If you are going to use different programming language, you'll have to implement listener
yourself. Below is core information you'll need:

All data transfer (incoming user transactions/outcoming bids) happens over
single websocket connection. Data is transfer in format of
[json-rpc](https://www.jsonrpc.org/specification).

To initiate connection, use url of the format like `ws://<hostname>/broadcaster/listen?token=<token>`,
replacing `<hostname>` with hostname of Wallchain auction and `<token>` with your authorization token.
After connection is opened, server will immediately start to send json-rpc notifications with method
`user_transaction`. Here is an example of such message:

```json
{
  "jsonrpc": "2.0",
  "method": "user_transaction",
  "params": {
    "lot_id": "id of lot to send back when making bid",
    "txn": {
      "from": "0x0000000000000000000000000000000000000000",
      "to": "0x0000000000000000000000000000000000000000",
      "value": "0x42",
      "input": "0x0"
    },
    "logs": [
      {
        "address": "0x0000000000000000000000000000000000000000",
        "topics": [
          "0x0000000000000000000000000000000000000000000000000000000000000000",
          "0x0000000000000000000000000000000000000000000000000000000000000000"
        ],
        "data": "0x0000000000000000000000000000000000000000000000000000000000000000"
      },
      {
        "address": "0x0000000000000000000000000000000000000000",
        "topics": [
          "0x0000000000000000000000000000000000000000000000000000000000000000",
          "0x0000000000000000000000000000000000000000000000000000000000000000"
        ],
        "data": "0x0000000000000000000000000000000000000000000000000000000000000000"
      }
    ]
  }
}
```

Here `params.txn` is information about user transaction,
and `params.logs` is result that collected by simulating this transaction.

After receiving such notification, you can execute your MEV searching logic.
If you found MEV and want to submit a bid, you should send json-rpc request
with method `make_bid`:

```json
{
  "jsonrpc": "2.0",
  "id": "id to track response",
  "method": "make_bid",
  "params": {
    "lot_id": "id of lot from user_transaction notification",
    "searcher_request": {
      "to": "hex address of searcher contract",
      "data": "calldata for searcher contract, as hex bytes",
      "gas": "amount of gas your contract may use, as int",
      "nonce": "random 256 bit number to prevent replay attacks on you, as hex",
      "bid": "amount of WETH you bid, e.g. willing to pay back, as hex",
      "user_call_hash": "hash of user transaction, as hex bytes",
      "max_gas_price": "max price per gas you are willing to pay, as hex",
      "deadline": "timestamp when your bid becomes invalid, as int"
    },
    "searcher_signature": "signature of searcher_request, as hex bytes"
  }
}
```

Please refer to python implementation to see exact logic how to calculate
`params.searcher_request.user_call_hash`, `params.searcher_signature`.

As json-rpc response, you are getting result of your bid verification:

```json
{
  "jsonrpc": "2.0",
  "id": "id to track response",
  "method": "make_bid",
  "result": {
    "verification_result": {
      "verified": true,
      "error_reason": null,
      "error_debug_info": null
    }
  }
}
```

If verification fails, field `result.verification_result.error_reason` will contain
short description of a problem, and `result.verification_result.error_debug_info` will contain
complete result of `debug_traceCall` with `callTracer`
([check format in Geth docs](https://geth.ethereum.org/docs/developers/evm-tracing/built-in-tracers#call-tracer)).

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

To run this example, you'll need to pass following parameters to the script:

| Parameter name     | Description                                                                             |
|--------------------|-----------------------------------------------------------------------------------------|
| --auction-url      | Base websocket url of the Wallchain auction. Should be something like ws://hostname     |
| --auction-token    | Authorization token for auction API                                                     |
| --capsule-address  | Address of Wallchain's capsule address, used to generate signatures                     |
| --contract-address | Address of searcher's contract                                                          |
| --private-key-hex  | Private key for searcher contract owner address. Used to sign SearcherRequest structure |

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

### Listener (python-sdk)

If you plan to use python for listener, you can base your code on `simple_searcher.py`.
If you do not want to use/do not like default CLI interface, you can use
`AuctionClient` class and `sign_searcher_request`, `user_tx_hash` helper functions
directly.

Your logic should generate and pass `SearcherRequest` object. Check the
comments in `simple_searcher.py` for descriptions of all fields. Note that:
- there is a minimal size of the bid, equal to **0.001 WBNB** for BSC chain.
- `SearcherRequest.deadline` should bid greater or equal then `SearcherInfo.min_deadline`

### Listener (websocket + jsonrpc)

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
    "lotId": "55f5af890bb58b09254df8049301ab687b0ee9ab",
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
    ],
    "minDeadline": 1693577243,
    "swapInfo": {
      "tokenIn":  "0x0000000000000000000000000000000000000000",
      "tokenOut":  "0x0000000000000000000000000000000000000000",
      "amountIn": "0x42",
      "nativeIn":  false
    }
  }
}
```

Here:
 - `params.lotId` is identifier of user transaction. It is used to match bids with auction lots.
 - `params.txn` is information about user transaction.
 - `params.logs` is result that collected by simulating this transaction.
 - `params.minDeadline` is timestamp, minimal deadline your bid should be valid. You
   should set `searcherRequest.deadline` to be greate or equal to this value.
   Note that this value is optional and can be missing in incoming notification.
 - `params.swapInfo` is information about swap that is represented by user transaction.
   Note that this value is optional and can be missing in incoming notification.

After receiving such notification, you can execute your MEV searching logic.
If you found MEV and want to submit a bid, you should send json-rpc request
with method `make_bid`:

```json
{
  "jsonrpc": "2.0",
  "id": "id to track response",
  "method": "make_bid",
  "params": {
    "lotId": "55f5af890bb58b09254df8049301ab687b0ee9ab",
    "searcherRequest": {
      "to": "0xEc730115C0D65ABfCc89642BcdabCAcD7E0E788C",
      "data": "0xfe0d94c100000000000000000000000000000000000000000000000000038d7ea4c68000",
      "gas": 1000000,
      "nonce": "0x4fb55a2cdc3dd31a55da10c6a2682b49fffb218558f3a2ad1fc1f2b7bec5a1fb",
      "bid": "0x38d7ea4c68000",
      "userCallHash": "0xcf1fd903ea8f7ce96a39f38016baa43419564872a92c8b6a22a0812637c41780",
      "maxGasPrice": "0x2540be400",
      "deadline": 1693577243
    },
    "searcherSignature": "0xb56963509a1b3e49ea1643686cb8cb6ec14ded8d7d8ddbaf53c04b86a324b10d2e0f7bdb5adb8a7a4449629b3bf1d30526b5ba275d620358a0630743b7cf8ed01c"
  }
}
```

Here:
 - `params.lotId` is identifier of user transaction. It is used to match bids with auction lots.
 - `params.searcherRequest.to` hex address of searcher contract
 - `params.searcherRequest.data` calldata for searcher contract, as hex bytes
 - `params.searcherRequest.gas` amount of gas your contract may use, as int. Your contract should have
   enough native token to pre-pay this amount of gas.
 - `params.searcherRequest.nonce` random 256 bit number to prevent replay attacks on you, as hex
 - `params.searcherRequest.bid` amount of WETH (wrapped native token) you bid,
                                 e.g. willing to pay back, as hex. Note that there
                                 are a **minimal** bid size. For BSC chain it is **0.001 WBNB**.
 - `params.searcherRequest.userCallHash` hash of user transaction, as hex bytes
 - `params.searcherRequest.maxGasPrice` max price per gas you are willing to pay, as hex
 - `params.searcherRequest.deadline` timestamp when your bid becomes invalid, as int
 - `params.searcherSignature` signature of searcher_request, as hex bytes

Please refer to python implementation to see exact logic how to calculate
`params.searcherRequest.userCallHash`, `params.searcherSignature`.

As json-rpc response, you are getting result of your bid verification:

```json
{
  "jsonrpc": "2.0",
  "id": "id to track response",
  "method": "make_bid",
  "result": {
    "verificationResult": {
      "verified": true,
      "errorReason": null,
      "errorDebugInfo": null
    }
  }
}
```

Here:
- `result.verificationResult.verified` flag, `true` if verification of bid was successful
- `result.verificationResult.errorReason` short description of problem if verification fails, otherwise `null`
- `result.verificationResult.errorDebugInfo` complete result of `debug_traceCall` with `callTracer`
([check format in Geth docs](https://geth.ethereum.org/docs/developers/evm-tracing/built-in-tracers#call-tracer)).

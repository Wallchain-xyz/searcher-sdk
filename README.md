# Wallchain's auction SDK for searchers

## Usage

```python
import asyncio
from typing import Optional
from datetime import datetime, timedelta
import secrets

from searcher_sdk import AuctionClient, SearcherInfo, BidData, SearcherRequest, user_tx_hash, sign_searcher_request


async def make_bid(info: SearcherInfo) -> Optional[BidData]:
    # your MEV search logic here
    request = SearcherRequest(
        bid=1000,                           # Your bid (amount of native token you pay)
        to="0x",                            # Your contract address
        data="0x",                          # Calldata for your contract
        user_call_hash=user_tx_hash(info),  # Hash of initial transaction for your safety
        deadline=int(                       # Timestamp when your bid becomes invalid
            (datetime.now() + timedelta(seconds=30)).timestamp()
        ),
        gas=1_000_000,                      # Max amount of gas you are going to spend
        max_gas_price=10,                   # Max gas price you accept
        nonce=secrets.randbits(256),        # Nonce to avoid replay attacks on you
    )
    return BidData(
        searcher_request=request,
                                            # To validate that bids comes from you, you'll need
                                            # to sign your request. Read example/simple_searcher.pyt
                                            # to see complete example.
        searcher_signature=sign_searcher_request(
            request, ...
        )
    )

asyncio.run(AuctionClient("wss://wallchain-auction-hostname", token="<your-token>").listen_lots(make_bid))
```

Complete working example can be found under `example/simple_searcher.py`.


## Development

### Setup

1. Install [tox](https://tox.wiki/en/4.6.4/installation.html):
```shell
python -m pip install pipx-in-pipx --user
pipx install tox
tox --help
```

### Developer workflow

#### Run lint and all tests
```shell
tox
```

#### Lint and auto-fix code
```shell
tox -e pre-commit
```

#### Run the unit test suite:
```shell
tox -e unit-py311
```

#### Run the integration test suite:
```shell
tox -e integration-py311
```

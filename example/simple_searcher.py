#!/usr/bin/env python3
import dataclasses
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

import click
from eth_utils import denoms

from searcher_sdk import (
    BaseSearcherConfig,
    CLISearcher,
    SearcherInfo,
    SearcherRequest,
    user_tx_hash,
)

logger = logging.getLogger()


@dataclasses.dataclass
class SimpleSearcherConfig(BaseSearcherConfig):
    contract_address: str


class SimpleSearcher(CLISearcher[SimpleSearcherConfig]):
    additional_click_options = [
        click.option(
            "--contract-address",
            help="Address of searcher's contract",
            required=True,
        )
    ]
    config_class = SimpleSearcherConfig

    async def _make_searcher_request(
        self, info: SearcherInfo
    ) -> Optional[SearcherRequest]:
        bid = 1 * denoms.milli
        return SearcherRequest(
            to=self._config.contract_address,  # Address of searchers contract
            data=(
                # Encoded calldata for searchers contract,
                f"0xfe0d94c1"
                + f"{bid:0>64x}"  # function selector + bid size
            ),
            bid=bid,  # Amount of WETH (wrapped native token) you pay
            user_call_hash=user_tx_hash(
                info
            ),  # Hash of user transaction for searchers safety
            deadline=(  # Timestamp, time until this searcher request is valid
                info.min_deadline
                or int((datetime.now() + timedelta(seconds=30)).timestamp())
            ),
            gas=1_000_000,  # Amount of gas searcher contract may use
            max_gas_price=5 * denoms.gwei,  # Max price searcher contract accepts.
            nonce=secrets.randbits(
                256
            ),  # A random number to protect from replay attacks
        )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s %(levelname).1s [%(process)d] "
            "l=%(name)s %(funcName)s() L%(lineno)-4d %(message)s"
        ),
    )

    SimpleSearcher.cli_entrypoint()

#!/usr/bin/env python3
import dataclasses
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

import click

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
        return SearcherRequest(
            data=(
                # This is hardcoded data to send 10**10 bid, TODO: un-hardcode it
                "0xfe0d94c1000000000000000000000000000"
                "00000000000000000000000000002540be400"
            ),
            bid=10**10,
            to=self._config.contract_address,
            user_call_hash=user_tx_hash(info),
            deadline=int((datetime.now() + timedelta(seconds=30)).timestamp()),
            gas=1_000_000,
            max_gas_price=5 * 10**9,
            nonce=secrets.randbits(256),
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    SimpleSearcher.cli_entrypoint()

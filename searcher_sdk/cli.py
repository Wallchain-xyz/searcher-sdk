import abc
import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable, ClassVar, Generic, Optional, Sequence, Type, TypeVar

import click

from searcher_sdk.client import AuctionClient
from searcher_sdk.models import (
    BidData,
    SearcherInfo,
    SearcherRequest,
    SignatureDomainInfo,
)
from searcher_sdk.utils import sign_searcher_request

logger = logging.getLogger()


@dataclass
class BaseSearcherConfig:
    domain_info: SignatureDomainInfo
    private_key_hex: str


CONFIG = TypeVar("CONFIG", bound=BaseSearcherConfig)
_AnyCallable = Callable[..., Any]


class CLISearcher(abc.ABC, Generic[CONFIG]):
    additional_click_options: ClassVar[
        Sequence[Callable[[_AnyCallable], _AnyCallable]]
    ] = ()
    config_class: Type[CONFIG]

    def __init__(
        self,
        client: AuctionClient,
        config: CONFIG,
        max_reconnects: int,
        reconnect_timeout: int,
    ) -> None:
        self._client = client
        self._config = config
        self._max_reconnects = max_reconnects
        self._reconnect_timeout = reconnect_timeout

    @abc.abstractmethod
    async def _make_searcher_request(
        self, info: SearcherInfo
    ) -> Optional[SearcherRequest]:
        pass

    async def _run_with_retries(self) -> None:
        for i in range(self._max_reconnects):
            try:
                await self.run_forever()
            except Exception as e:
                logger.exception(e)
            logger.warning(
                f"Used {i + 1} connect tries. "
                f"Reconnecting in {self._reconnect_timeout} seconds"
            )
            await asyncio.sleep(self._reconnect_timeout)

    async def run_forever(self) -> None:
        logger.info("Starting listening for lots indefinitely")
        async with self._client:
            async for info in self._client.listen_as_iter():
                with info.enter_context_maybe():
                    await self._on_searcher_info(info)

    async def _on_searcher_info(self, info: SearcherInfo) -> None:
        logger.info(f"Got lot: {info}")
        request = await self._make_searcher_request(info)
        if request is None:
            return
        bid_data = BidData(
            searcher_request=request,
            searcher_signature=sign_searcher_request(
                request=request,
                domain_info=self._config.domain_info,
                private_key_hex=self._config.private_key_hex,
            ),
        )
        result = await self._client.make_bid(info.lot_id, bid_data)
        logger.info(f"Got make bid result: {result}")

    @classmethod
    def cli_entrypoint(cls) -> None:
        @click.option(
            "--auction-url",
            help=(
                "Base websocket url of the Wallchain auction. "
                "Should be something like ws://hostname"
            ),
            required=True,
        )
        @click.option(
            "--auction-token",
            help=("Authorization token for auction API"),
            required=True,
        )
        @click.option(
            "--chain-id",
            type=int,
            help="Chain id, used to generate signatures. Default is BNB",
            default=0x38,
        )
        @click.option(
            "--capsule-address",
            help="Address of Wallchain's capsule address, used to generate signatures",
            required=True,
        )
        @click.option(
            "--private-key-hex",
            help=(
                "Private key for searcher contract owner address. "
                "Used to sign SearcherRequest structure"
            ),
            required=True,
            type=str,
        )
        @click.option(
            "--otel-enabled",
            envvar="OTEL_ENABLED",
            help="Enable generation of OpenTelemetry spans",
            is_flag=True,
            default=False,
        )
        @click.option(
            "--otel-exporter-otlp-endpoint",
            envvar="OTEL_EXPORTER_OTLP_ENDPOINT",
            help="OpenTelemetry exporter grpc endpoint",
            type=str,
        )
        @click.option(
            "--max-reconnects",
            help="Maximum number of reconnects before process exists",
            type=int,
            default=10,
        )
        @click.option(
            "--reconnect-timeout",
            help="Wait this many seconds before reconnecting",
            type=int,
            default=5,
        )
        def start_searcher(
            auction_url: str,
            auction_token: str,
            chain_id: int,
            capsule_address: str,
            private_key_hex: str,
            otel_enabled: bool,
            otel_exporter_otlp_endpoint: Optional[str],
            max_reconnects: int,
            reconnect_timeout: int,
            **kwargs: Any,
        ) -> None:
            """Start searcher for Wallchain MEV auction"""

            if otel_enabled:
                try:
                    from searcher_sdk.tracing import TracingConfig, setup_tracing
                except ImportError:
                    raise ValueError(
                        "To be able to use --otlp-enabled you should"
                        " install sdk with tracing support:"
                        "pip install searcher-sdk[tracing]"
                    )
                setup_tracing(
                    TracingConfig(
                        service_name="simple_searcher",
                        otlp_exporter_endpoint=otel_exporter_otlp_endpoint,
                    )
                )

            searcher = cls(
                client=AuctionClient(auction_url, auction_token),
                config=cls.config_class(
                    domain_info=SignatureDomainInfo(
                        chain_id=chain_id,
                        contract_addr=capsule_address,
                    ),
                    private_key_hex=private_key_hex,
                    **kwargs,
                ),
                max_reconnects=max_reconnects,
                reconnect_timeout=reconnect_timeout,
            )

            asyncio.run(searcher._run_with_retries())

        for additional_option in cls.additional_click_options:
            start_searcher = additional_option(start_searcher)

        click.command(start_searcher)()

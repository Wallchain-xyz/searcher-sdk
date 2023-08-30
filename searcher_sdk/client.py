import asyncio
import datetime
import logging
from contextlib import ExitStack
from typing import Awaitable, Callable, Optional, Set

from websockets.client import connect

from searcher_sdk.jsonrpc import JSONRPCClient
from searcher_sdk.models import (
    BidData,
    MakeBidParam,
    MakeBidResult,
    SearcherInfo,
    SearcherInfoWithTraceContext,
)

try:
    from opentelemetry import trace
    from opentelemetry.propagate import extract
    from opentelemetry.trace import Tracer

    tracer: Optional[Tracer] = trace.get_tracer(__name__)
except ImportError:
    tracer = None

logger = logging.getLogger(__name__)

BidMaker = Callable[[SearcherInfo], Awaitable[Optional[BidData]]]
ResultListener = Callable[[MakeBidResult], Awaitable[None]]


class PingNotReceived(Exception):
    pass


class AuctionClient:
    _url: str
    _id: int
    _tasks: Set["asyncio.Task[None]"]
    _message_timeout: float  # Timeout to also read exceptions

    def __init__(
        self,
        url: str,
        token: str,
        ping_interval: datetime.timedelta = datetime.timedelta(seconds=10),
        ping_timeout: datetime.timedelta = datetime.timedelta(seconds=5),
    ) -> None:
        self._url = url
        self._token = token
        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout
        self._bid_maker: Optional[BidMaker] = None
        self._result_listener: Optional[ResultListener] = None
        self._json_rpc_client = JSONRPCClient()
        self._json_rpc_client.on_notification("user_transaction")(self._process_lot)

    async def _process_lot(self, info: SearcherInfoWithTraceContext) -> None:
        assert self._bid_maker, "_process_lot() called before listen_lots()"
        with ExitStack() as stack:
            if info.trace_data and tracer:
                trace_ctx = extract(info.trace_data)
                logger.info(f"Using trace context {trace_ctx}")
                stack.enter_context(
                    tracer.start_as_current_span("process_lot", context=trace_ctx)
                )
            bid = await self._bid_maker(SearcherInfo(**info.model_dump()))
            if bid is not None:
                result = await self._json_rpc_client.send_request(
                    "make_bid",
                    MakeBidParam(
                        lot_id=info.lot_id,
                        searcher_request=bid.searcher_request,
                        searcher_signature=bid.searcher_signature,
                    ),
                )
                if self._result_listener:
                    await self._result_listener(MakeBidResult(**result))

    async def _ping_loop(self) -> None:
        while True:
            try:
                res = await asyncio.wait_for(
                    self._json_rpc_client.send_request("ping"),
                    timeout=self._ping_timeout.total_seconds(),
                )
            except asyncio.TimeoutError:
                raise PingNotReceived(
                    f"Broken connection: did not received ping in "
                    f"{self._ping_timeout.total_seconds()} seconds"
                )
            if res != "pong":
                logger.warning(f"Wrong ping response: {res}")
            await asyncio.sleep(self._ping_interval.total_seconds())

    async def listen_lots(
        self, bid_maker: BidMaker, result_listener: Optional[ResultListener] = None
    ) -> None:
        self._bid_maker = bid_maker
        self._result_listener = result_listener
        async with connect(
            self._url + f"/broadcaster/listen?token={self._token}"
        ) as ws:
            async with self._json_rpc_client.listen(ws):
                await self._ping_loop()

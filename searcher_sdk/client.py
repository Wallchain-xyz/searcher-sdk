import asyncio
import datetime
import logging
from contextlib import AsyncExitStack
from typing import Any, AsyncIterator, Awaitable, Callable, Optional, Set

from websockets.client import connect

from searcher_sdk.jsonrpc import JSONRPCClient
from searcher_sdk.models import (
    BidData,
    MakeBidParam,
    MakeBidResult,
    SearcherInfo,
    SearcherInfoWithTraceContext,
)
from searcher_sdk.utils import cancel_on_exit

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
        self._connected: bool = False
        self._json_rpc_client = JSONRPCClient()
        self._exit_stack = AsyncExitStack()
        self._queue: "asyncio.Queue[SearcherInfoWithTraceContext | PingNotReceived]" = (
            asyncio.Queue()
        )

    async def listen_lots(
        self, bid_maker: BidMaker, result_listener: Optional[ResultListener] = None
    ) -> None:
        async with self:  # Connect, no-op if already connected
            async for info in self.listen_as_iter():
                await self._process_info(info, bid_maker, result_listener)

    async def make_bid(self, lot_id: str, bid: BidData) -> MakeBidResult:
        res = await self._json_rpc_client.send_request(
            "make_bid",
            MakeBidParam(
                lot_id=lot_id,
                searcher_request=bid.searcher_request,
                searcher_signature=bid.searcher_signature,
            ),
        )
        return MakeBidResult(**res)

    async def listen_as_iter(self) -> AsyncIterator[SearcherInfoWithTraceContext]:
        while True:
            item = await self._queue.get()
            if isinstance(item, PingNotReceived):
                raise item
            yield item

    async def __aenter__(self) -> "AuctionClient":
        if not self._connected:
            self._json_rpc_client = JSONRPCClient()
            self._exit_stack = AsyncExitStack()
            self._queue = asyncio.Queue()

            self._json_rpc_client.on_notification("user_transaction")(self._process_lot)
            await self._exit_stack.__aenter__()
            ws = await self._exit_stack.enter_async_context(
                connect(self._url + f"/broadcaster/listen?token={self._token}")
            )
            await self._exit_stack.enter_async_context(self._json_rpc_client.listen(ws))
            await self._exit_stack.enter_async_context(
                cancel_on_exit(self._ping_loop())
            )
            self._connected = True
        return self

    async def __aexit__(self, *args: Any) -> None:
        try:
            await self._exit_stack.__aexit__(*args)
        finally:
            self._connected = False

    async def _ping_loop(self) -> None:
        while True:
            try:
                logger.info("Sending ping")
                res = await asyncio.wait_for(
                    self._json_rpc_client.send_request("ping"),
                    timeout=self._ping_timeout.total_seconds(),
                )
                logger.info("Got pong")
            except asyncio.TimeoutError:
                await self._queue.put(
                    PingNotReceived(
                        f"Broken connection: did not received ping in "
                        f"{self._ping_timeout.total_seconds()} seconds"
                    )
                )
                return
            except Exception:
                await self._queue.put(
                    PingNotReceived(f"Broken connection: failed to send ping")
                )
                return
            if res != "pong":
                logger.warning(f"Wrong ping response: {res}")
            await asyncio.sleep(self._ping_interval.total_seconds())

    async def _process_lot(self, info: SearcherInfoWithTraceContext) -> None:
        await self._queue.put(info)

    async def _process_info(
        self,
        info: SearcherInfoWithTraceContext,
        bid_maker: BidMaker,
        result_listener: Optional[ResultListener] = None,
    ) -> None:
        try:
            with info.enter_context_maybe():
                bid = await bid_maker(SearcherInfo(**info.model_dump()))
                if bid is None:
                    return
                result = await self.make_bid(info.lot_id, bid)
                if result_listener:
                    await result_listener(result)
        except Exception:
            logger.exception("Failed to process searcher info")

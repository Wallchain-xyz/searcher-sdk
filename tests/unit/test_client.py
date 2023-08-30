import asyncio
import contextlib
import dataclasses
import datetime
import threading
import time
from multiprocessing import Queue
from queue import Empty
from typing import Any, Dict, Iterator, List

import pytest
import uvicorn
from fastapi import FastAPI, WebSocket
from starlette.websockets import WebSocketDisconnect

from searcher_sdk import AuctionClient, BidData, SearcherInfo, SearcherRequest
from searcher_sdk.client import PingNotReceived
from searcher_sdk.utils import cancel_on_exit

from tests.helpers import BidDataFactory, SearcherInfoFactory, wait_for_condition


class Server(uvicorn.Server):
    """Uvicorn server class that allows running in thread for testing"""

    should_exit: bool

    def install_signal_handlers(self) -> None:
        pass

    @contextlib.contextmanager
    def run_in_thread(self) -> Iterator[None]:
        """Run server in a thread"""
        thread = threading.Thread(target=self.run)
        thread.start()
        try:
            while not self.started:
                if self.should_exit:
                    raise Exception("Failed to start server")
                time.sleep(1e-3)
            yield
        finally:
            self.should_exit = True
            thread.join()


@dataclasses.dataclass
class MockAuctionServer:
    url: str
    received: List[Dict[str, Any]]
    send_queue: Queue  # type: ignore


@pytest.fixture
def fake_server() -> Iterator[MockAuctionServer]:
    app = FastAPI()

    server = MockAuctionServer(
        url="",
        received=[],
        send_queue=Queue(),
    )

    @app.websocket("/broadcaster/listen")
    async def handle_request(websocket: WebSocket) -> None:
        await websocket.accept()

        async def _sender() -> None:
            while True:
                try:
                    message_to_send = await asyncio.get_event_loop().run_in_executor(
                        None, server.send_queue.get, True, 0.1
                    )
                except Empty:
                    pass
                else:
                    await websocket.send_json(message_to_send)

        async with cancel_on_exit(_sender()):
            try:
                while True:
                    message = await websocket.receive_json()
                    server.received.append(message)
            except WebSocketDisconnect:
                pass

    uvicorn_server = Server(uvicorn.Config(app, port=8001))
    with uvicorn_server.run_in_thread():
        server.url = f"ws://{uvicorn_server.config.host}:{uvicorn_server.config.port}"
        yield server


async def test_lots_received(fake_server: MockAuctionServer) -> None:
    # Arrange
    info: SearcherInfo = SearcherInfoFactory.build()
    fake_server.send_queue.put_nowait(
        {
            "method": "user_transaction",
            "params": info.model_dump(),
        }
    )

    async def make_bid(info_received: SearcherInfo) -> None:
        infos_received.append(info_received)

    client = AuctionClient(fake_server.url, "token")
    infos_received: List[SearcherInfo] = []

    # Act
    async with cancel_on_exit(client.listen_lots(make_bid)):
        await wait_for_condition(lambda: bool(infos_received))

    # Assert
    assert info in infos_received


async def test_bid_sent(fake_server: MockAuctionServer) -> None:
    # Arrange
    info: SearcherInfo = SearcherInfoFactory.build()
    bid: BidData = BidDataFactory.build()
    fake_server.send_queue.put_nowait(
        {
            "method": "user_transaction",
            "params": info.model_dump(),
        }
    )

    async def make_bid(_: SearcherInfo) -> BidData:
        return bid

    client = AuctionClient(fake_server.url, "token")

    # Act
    async with cancel_on_exit(client.listen_lots(make_bid)):
        await wait_for_condition(
            lambda: any(mess["method"] == "make_bid" for mess in fake_server.received)
        )

    # Assert
    message_raw = next(
        mess["params"] for mess in fake_server.received if mess["method"] == "make_bid"
    )

    assert info.lot_id == message_raw["lot_id"]
    assert message_raw["searcher_request"]["nonce"] == hex(bid.searcher_request.nonce)
    assert message_raw["searcher_request"]["bid"] == hex(bid.searcher_request.bid)
    assert message_raw["searcher_request"]["maxGasPrice"] == hex(
        bid.searcher_request.max_gas_price
    )
    assert bid.searcher_request == SearcherRequest(**message_raw["searcher_request"])
    assert bid.searcher_signature == message_raw["searcher_signature"]


async def test_ping_pong(fake_server: MockAuctionServer) -> None:
    # Arrange
    async def make_bid(_: SearcherInfo) -> None:
        pass

    client = AuctionClient(
        fake_server.url,
        "token",
        ping_interval=datetime.timedelta(seconds=0.01),
    )

    # Act
    async with cancel_on_exit(client.listen_lots(make_bid)):
        for _ in range(5):
            await wait_for_condition(lambda: bool(fake_server.received))
            fake_server.send_queue.put_nowait(
                {
                    "id": fake_server.received[0]["id"],
                    "result": "pong",
                }
            )
            fake_server.received.pop(0)


async def test_ping_pong_auto_disconnect(fake_server: MockAuctionServer) -> None:
    # Arrange
    async def make_bid(_: SearcherInfo) -> None:
        pass

    client = AuctionClient(
        fake_server.url,
        "token",
        ping_timeout=datetime.timedelta(seconds=0.1),
    )

    # Act
    with pytest.raises(PingNotReceived):
        await asyncio.wait_for(client.listen_lots(make_bid), timeout=1)

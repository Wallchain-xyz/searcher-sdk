import asyncio
import datetime
import enum
import inspect
import logging as L
import secrets
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional, Union

from pydantic import BaseModel, TypeAdapter
from websockets.legacy.client import WebSocketClientProtocol

from searcher_sdk.utils import cancel_on_exit

logger = L.getLogger(__name__)


IdType = Union[str, int, float]


class JSONRPCNotification(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Optional[Any]


class JSONRPCRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[IdType] = None
    method: str
    params: Optional[Any] = None


class JSONRPCResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[IdType] = None
    result: Optional[Any]


class JSONRPCError(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None


class JSONRPCErrorResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[IdType] = None
    error: JSONRPCError


AnyJsonRPCMessage = Union[
    JSONRPCNotification, JSONRPCRequest, JSONRPCResponse, JSONRPCErrorResponse
]


class ErrorCodes(enum.Enum):
    """JSON-RPC 2.0 error codes

    More info: https://www.jsonrpc.org/specification#error_object
    """

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32601
    SERVER_ERROR = -32000


class RpcMethod(BaseModel):
    method_name: str
    input_type: Any
    handler: Callable[[Any], Awaitable[Any]]

    @classmethod
    def from_function(cls, func: Any) -> "RpcMethod":
        signature = inspect.signature(func)
        assert inspect.iscoroutinefunction(
            func
        ), "RPC handler should be coroutine functions"
        assert len(signature.parameters) == 1, "RPC handler can have only one parameter"
        param = next(iter(signature.parameters.values()))
        return cls(
            method_name=func.__name__,
            input_type=param.annotation,
            handler=func,
        )

    def prepare_param(self, data: Any) -> Any:
        if self.input_type is None:
            return None
        elif issubclass(self.input_type, BaseModel):
            return self.input_type(**data)
        else:
            raise Exception("Unsupported input type")


class JSONRPCClient:
    def __init__(
        self, response_timeout: datetime.timedelta = datetime.timedelta(seconds=10)
    ) -> None:
        self._ws: Optional[WebSocketClientProtocol] = None
        self._res_futures: Dict[IdType, "asyncio.Future[Any]"] = {}
        self._notification_listeners: Dict[str, List[RpcMethod]] = defaultdict(list)
        self._response_timeout = response_timeout

    def on_notification(self, method: str) -> Callable[[Any], Any]:
        def register(listener: Any) -> Any:
            self._notification_listeners[method].append(
                RpcMethod.from_function(listener)
            )
            return listener

        return register

    async def send_request(
        self,
        method: str,
        params: Optional[BaseModel] = None,
    ) -> Any:
        assert self._ws, "listen() should be called before using send_request"
        req_id = secrets.token_hex(4)
        req = JSONRPCRequest(
            id=req_id,
            method=method,
            params=params,
        )
        future: "asyncio.Future[Any]" = asyncio.Future()
        self._res_futures[req_id] = future
        await self._ws.send(req.model_dump_json(by_alias=True))
        result = await asyncio.wait_for(
            future, timeout=self._response_timeout.total_seconds()
        )
        return result

    @asynccontextmanager
    async def listen(self, ws: WebSocketClientProtocol) -> AsyncIterator[None]:
        self._ws = ws
        async with cancel_on_exit(self._listen_incoming()):
            yield

    async def _listen_incoming(self) -> None:
        assert self._ws, "listen() should be called before using send_request"
        while True:
            try:
                raw = await self._ws.recv()
            except Exception as e:
                # Fail all futures for pending requests, as they
                # will never receive response
                for key, future in list(self._res_futures.items()):
                    if not future.done():
                        self._res_futures.pop(key)
                        future.set_exception(e)
                raise e
            if raw is None:
                continue
            asyncio.create_task(self._handle_raw_message(raw))

    async def _handle_raw_message(self, raw: Union[str, bytes]) -> None:
        try:
            try:
                message = TypeAdapter(AnyJsonRPCMessage).validate_json(raw)
            except ValueError:
                logger.warning(f"Got invalid json-rpc message from server: {raw!r}")
                return
            if isinstance(message, JSONRPCNotification):
                await self._handle_notification(message)
            if isinstance(message, JSONRPCRequest):
                await self._handle_request(message)
            if isinstance(message, JSONRPCResponse):
                await self._handle_response(message)
            if isinstance(message, JSONRPCErrorResponse):
                await self._handle_error(message)
        except Exception:
            logger.exception("Error during processing JSON RPC message")

    async def _handle_notification(self, message: JSONRPCNotification) -> None:
        for listener in self._notification_listeners.get(message.method, []):
            param = listener.prepare_param(message.params)
            await listener.handler(param)

    async def _handle_request(self, message: JSONRPCRequest) -> None:
        logger.warning("Incoming JSONRPC request are not supported")

    async def _handle_response(self, message: JSONRPCResponse) -> None:
        if message.id is None:
            return
        future = self._res_futures.pop(message.id)
        if future:
            future.set_result(message.result)
        else:
            logger.warning(f"Got JSON-RPC response for unknown id {message.id}")

    async def _handle_error(self, message: JSONRPCErrorResponse) -> None:
        logger.warning(
            f"Got error JSON-RPC response: id={message.id} "
            f"error.message={message.error.message}"
            f"error.code={message.error.code}"
            f"error.data={message.error.data}"
        )

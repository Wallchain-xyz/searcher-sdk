import logging as L
from contextlib import ExitStack, contextmanager
from typing import Any, Iterator, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from searcher_sdk.pydantic_annotations import HexInt, HexStr

try:
    from opentelemetry import trace
    from opentelemetry.propagate import extract
    from opentelemetry.trace import Tracer

    tracer: Optional[Tracer] = trace.get_tracer(__name__)
except ImportError:
    tracer = None


logger = L.getLogger(__name__)

TRACING_CTX_KEY = "__tracing_context__"


class Txn(BaseModel):
    from_: HexStr = Field(alias="from")
    to: HexStr
    value: HexInt
    input: HexStr

    model_config = ConfigDict(populate_by_name=True)


class TxnLog(BaseModel):
    address: HexStr
    topics: List[HexStr]
    data: HexStr


class SwapInfo(BaseModel):
    token_in: HexStr = Field(alias="tokenIn")
    token_out: HexStr = Field(alias="tokenOut")
    amount_in: HexInt = Field(alias="amountIn")
    native_in: bool = Field(alias="nativeIn")

    model_config = ConfigDict(populate_by_name=True)


class SearcherInfo(BaseModel):
    lot_id: str = Field(alias="lotId")
    txn: Txn
    logs: List[TxnLog]
    min_deadline: Optional[int] = Field(alias="minDeadline", default=None)
    swap_info: Optional[SwapInfo] = Field(alias="swapInfo", default=None)

    model_config = ConfigDict(populate_by_name=True)


class SearcherInfoWithTraceContext(SearcherInfo):
    trace_data: Optional[Any] = Field(alias=TRACING_CTX_KEY, default=None)

    @contextmanager
    def enter_context_maybe(self) -> Iterator[None]:
        with ExitStack() as stack:
            if self.trace_data and tracer:
                trace_ctx = extract(self.trace_data)
                logger.info(f"Using trace context {trace_ctx}")
                stack.enter_context(
                    tracer.start_as_current_span("process_lot", context=trace_ctx)
                )
            yield None


class SearcherRequest(BaseModel):
    to: HexStr
    gas: int
    nonce: HexInt
    data: HexStr
    bid: HexInt
    user_call_hash: HexStr = Field(alias="userCallHash")
    max_gas_price: HexInt = Field(alias="maxGasPrice")
    deadline: int

    model_config = ConfigDict(populate_by_name=True)


class BidData(BaseModel):
    searcher_request: SearcherRequest
    searcher_signature: HexStr


class MakeBidParam(BaseModel):
    lot_id: str = Field(alias="lotId")
    searcher_request: SearcherRequest = Field(alias="searcherRequest")
    searcher_signature: HexStr = Field(alias="searcherSignature")

    model_config = ConfigDict(populate_by_name=True)


class VerificationResult(BaseModel):
    verified: bool
    error_reason: Optional[str] = Field(alias="errorReason", default=None)
    error_debug_info: Optional[str] = Field(alias="errorDebugInfo", default=None)

    model_config = ConfigDict(populate_by_name=True)


class MakeBidResult(BaseModel):
    verification_result: Optional[VerificationResult] = Field(
        alias="verificationResult", default=None
    )

    model_config = ConfigDict(populate_by_name=True)


class SignatureDomainInfo(BaseModel):
    type_schema: str = (
        "EIP712Domain(string name,string version,uint256 chainId,"
        "address verifyingContract)"
    )
    name: str = "SearcherExecutionCapsule"
    version: str = "1"
    contract_addr: HexStr
    chain_id: int

from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from searcher_sdk.pydantic_annotations import HexInt, HexStr

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


class SearcherInfo(BaseModel):
    lot_id: str
    txn: Txn
    logs: List[TxnLog]


class SearcherInfoWithTraceContext(SearcherInfo):
    trace_data: Optional[Any] = Field(alias=TRACING_CTX_KEY, default=None)


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
    lot_id: str
    searcher_request: SearcherRequest
    searcher_signature: HexStr


class VerificationResult(BaseModel):
    verified: bool
    error_reason: Optional[str] = None
    error_debug_info: Optional[str] = None


class MakeBidResult(BaseModel):
    verification_result: Optional[VerificationResult] = None


class SignatureDomainInfo(BaseModel):
    type_schema: str = (
        "EIP712Domain(string name,string version,uint256 chainId,"
        "address verifyingContract)"
    )
    name: str = "SearcherExecutionCapsule"
    version: str = "1"
    contract_addr: HexStr
    chain_id: int

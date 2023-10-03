import asyncio
from contextlib import asynccontextmanager, suppress
from typing import Any, AsyncIterator, Coroutine

import eth_account
from eth_abi import encode
from eth_abi.packed import encode_packed
from eth_account.messages import SignableMessage
from eth_utils import keccak
from hexbytes import HexBytes

from searcher_sdk.models import SearcherInfo, SearcherRequest, SignatureDomainInfo


def hex_str_to_bytes(val: str) -> bytes:
    if val.startswith("0x"):
        val = val[2:]
    return bytes.fromhex(val.lower())


def bytes_to_hex_str(val: bytes) -> str:
    return "0x" + val.hex()


def user_tx_hash(info: SearcherInfo) -> str:
    return bytes_to_hex_str(
        keccak(
            encode_packed(
                ["address", "bytes", "uint256"],
                (
                    hex_str_to_bytes(info.txn.to),
                    hex_str_to_bytes(info.txn.input),
                    info.txn.value,
                ),
            )
        )
    )


def sign_searcher_request(
    request: SearcherRequest, domain_info: SignatureDomainInfo, private_key_hex: str
) -> str:
    message_hash = keccak(
        encode(
            [
                "bytes32",
                "address",
                "uint256",
                "uint256",
                "bytes32",
                "uint256",
                "bytes32",
                "uint256",
                "uint256",
            ],
            [
                keccak(
                    b"SearcherRequest(address to,uint256 gas,uint256 nonce,"
                    b"bytes data,uint256 bid,bytes32 userCallHash,"
                    b"uint256 maxGasPrice, uint256 deadline)"
                ),
                hex_str_to_bytes(request.to),
                request.gas,
                request.nonce,
                keccak(hex_str_to_bytes(request.data)),
                request.bid,
                hex_str_to_bytes(request.user_call_hash),
                request.max_gas_price,
                request.deadline,
            ],
        )
    )

    singable_message = SignableMessage(
        HexBytes(b"\x01"),
        HexBytes(_get_domain_hash(domain_info)),
        HexBytes(message_hash),
    )

    return eth_account.Account.sign_message(
        singable_message, private_key_hex
    ).signature.hex()


def _get_domain_hash(domain_info: SignatureDomainInfo) -> bytes:
    return keccak(
        encode(
            ["bytes32", "bytes32", "bytes32", "uint", "address"],
            [
                keccak(domain_info.type_schema.encode()),
                keccak(domain_info.name.encode()),
                keccak(domain_info.version.encode()),
                domain_info.chain_id,
                domain_info.contract_addr,
            ],
        )
    )


@asynccontextmanager
async def cancel_on_exit(
    coro: Coroutine[Any, Any, Any], timeout_sec: float = 5
) -> AsyncIterator["asyncio.Task[Any]"]:
    task = asyncio.create_task(coro)
    try:
        yield task
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=timeout_sec)

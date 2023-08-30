import secrets
from datetime import datetime

from searcher_sdk.models import SearcherInfo, SearcherRequest, SignatureDomainInfo, Txn
from searcher_sdk.utils import sign_searcher_request, user_tx_hash


def _make_random_addr() -> str:
    return "0x" + secrets.token_bytes(20).hex()


def test_user_tx_hash() -> None:
    # Arrange
    info = SearcherInfo(
        lot_id="1",
        txn=Txn(
            **{
                "from": _make_random_addr(),
                "to": "0xf8e81D47203A594245E36C48e151709F0C19fBe8",
                "value": 0,
                "input": "0x4242",
            }
        ),
        logs=[],
    )

    # Act
    hash = user_tx_hash(info)

    # Assert
    assert hash == "0x15168fc51e3196519c6c3174da94796fe0f75403aa1011a6b0eef67fb4212087"


def test_sign_req() -> None:
    # Arrange
    info = SearcherInfo(
        lot_id="1",
        txn=Txn(
            from_=_make_random_addr(),
            to=_make_random_addr(),
            value=0,
            input="0x4242",
        ),
        logs=[],
    )
    req = SearcherRequest(
        bid=1000,
        data="0x",
        to=_make_random_addr(),
        user_call_hash=user_tx_hash(info),
        deadline=int((datetime(day=1, month=1, year=2023)).timestamp()),
        gas=1_000_000,
        max_gas_price=10,
        nonce=42,
    )
    domain = SignatureDomainInfo(
        contract_addr=_make_random_addr(),
        chain_id=0x1,
    )
    private_key = "0x" + secrets.token_hex(32)

    # Act

    signature = sign_searcher_request(
        request=req,
        domain_info=domain,
        private_key_hex=private_key,
    )

    # Assert

    # TODO: use same private key and validate signature
    assert signature

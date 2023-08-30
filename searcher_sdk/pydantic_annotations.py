from typing import Union

from pydantic import AfterValidator, PlainSerializer, PlainValidator
from typing_extensions import Annotated


def check_starts_with_0x(v: str) -> str:
    assert v.startswith("0x"), "Hex bytes string should start with 0x"
    return v


def check_valid_bytes(v: str) -> str:
    bytes.fromhex(v[len("0x") :].lower())
    return v


HexStr = Annotated[
    str,
    AfterValidator(check_starts_with_0x),
    AfterValidator(check_valid_bytes),
]


def _parse_hex_int(value: Union[int, str]) -> int:
    if isinstance(value, int):
        return value
    if value.startswith("0x"):
        value = value[2:]
    return int(value, 16)


HexInt = Annotated[
    int, PlainValidator(_parse_hex_int), PlainSerializer(lambda x: hex(x))
]

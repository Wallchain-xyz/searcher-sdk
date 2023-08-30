import asyncio
import secrets
import time
from typing import Any, Callable, Dict, Generic, Type, TypeVar

from polyfactory.factories.pydantic_factory import ModelFactory
from pydantic import BaseModel

from searcher_sdk import BidData, SearcherInfo


async def wait_for_condition(
    condition: Callable[[], bool], timeout: float = 0.1
) -> bool:
    start = time.time()
    while (time.time() - start) < timeout:
        if condition():
            return True
        await asyncio.sleep(0.01)
    return False


T = TypeVar("T", bound=BaseModel)


class CustomModelFactory(Generic[T], ModelFactory[T]):
    __is_base_factory__ = True

    @classmethod
    def get_provider_map(cls) -> Dict[Type[Any], Any]:
        providers_map = super().get_provider_map()

        return {
            **providers_map,
            str: lambda: "0x" + secrets.token_bytes(20).hex(),
        }


class SearcherInfoFactory(CustomModelFactory[SearcherInfo]):
    __model__ = SearcherInfo


class BidDataFactory(CustomModelFactory[BidData]):
    __model__ = BidData

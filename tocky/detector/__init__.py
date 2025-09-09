from typing import TypeVar
from tocky.utils.phase import AbstractPhase

TParams = TypeVar("TParams")

class AbstractDetector(AbstractPhase[TParams]):
    def detect(self, ocaid: str) -> list[int]:
        raise NotImplementedError()

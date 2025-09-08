from typing import Generic, TypeVar
from tocky.utils import ShareableState

TParams = TypeVar("TParams")

class AbstractDetector(Generic[TParams]):
    name: str
    P: TParams
    S: ShareableState
    debug = True
    """
    When debug is set to true, extra helper variables could be set
    """

    def __init__(self):
        self.S = ShareableState()

    def detect(self, ocaid: str) -> list[int]:
        raise NotImplementedError()

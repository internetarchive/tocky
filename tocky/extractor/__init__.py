from dataclasses import dataclass
from typing import Generic, TypeVar

from tocky.utils import ShareableState


@dataclass
class TocResponse:
  toc: str
  prompt_tokens: int
  completion_tokens: int


TParams = TypeVar("TParams")

class AbstractExtractor(Generic[TParams]):
    name: str
    P: TParams
    S: ShareableState
    debug = True
    """
    When debug is set to true, extra helper variables could be set
    """

    def __init__(self):
        self.S = ShareableState()

    toc_raw_ocr: list[str] | None = None
    toc_response: TocResponse | None = None

    def predict_cost(self) -> float:
        raise NotImplementedError()

    def extract(self, ocaid: str, detector_result: list[int]) -> str:
        raise NotImplementedError()

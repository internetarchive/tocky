from dataclasses import dataclass, field

from tocky.detector import AbstractDetector


@dataclass
class ManualDetectorOptions:
    leaf_numbers: list[int] = field(default_factory=list)


class ManualDetector(AbstractDetector[ManualDetectorOptions]):
    P = ManualDetectorOptions()

    def predict_cost(self):
        return 0.0

    def detect(self, ocaid: str):
        return self.P.leaf_numbers

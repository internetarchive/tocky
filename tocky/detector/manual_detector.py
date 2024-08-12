from dataclasses import dataclass

from tocky.detector import AbstractDetector


@dataclass
class ManualDetectorOptions:
    leaf_numbers: list[int]


class ManualDetector(AbstractDetector[ManualDetectorOptions]):
    P: ManualDetectorOptions

    def predict_cost(self):
        return 0.0

    def detect(self, ocaid: str):
        return self.P.leaf_numbers

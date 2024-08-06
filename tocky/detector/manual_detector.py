from dataclasses import dataclass


@dataclass
class ManualDetectorOptions:
    leaf_numbers: list[int]


class ManualDetector:
    P: ManualDetectorOptions

    def detect(self, ocaid: str):
        return self.P.leaf_numbers

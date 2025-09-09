from tocky.detector import AbstractDetector
from tocky.detector.ai_vision_detector import AiVisionDetector
from tocky.detector.manual_detector import ManualDetector
from tocky.detector.ocr_detector import OcrDetector
from tocky.extractor import AbstractExtractor
from tocky.extractor.ai_extractor import AiExtractor
from tocky.extractor.ai_vision_extractor import AiVisionExtractor


DETECTERS: list[type[AbstractDetector]] = [
    OcrDetector,
    AiVisionDetector,
    ManualDetector,
]

EXTRACTORS: list[type[AbstractExtractor]] = [
    AiExtractor,
    AiVisionExtractor,
]

DETECTERS_BY_NAME = {d.name: d for d in DETECTERS}
EXTRACTORS_BY_NAME = {e.name: e for e in EXTRACTORS}

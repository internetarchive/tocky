from dataclasses import dataclass
from typing import Literal

from PIL import Image
from lxml import etree

from tocky.detector.ai_vision_detector import image_to_base64
from tocky.extractor import AbstractExtractor, TocEntry, TocResponse
from tocky.extractor.formats import build_system_prompt, process_extracted_output
from tocky.ocr.printer import print_ocr
from tocky.utils.ia import get_book_images, get_djvu_by_leaf_nums, ocaid_to_djvu_url
from tocky.utils.llm import hit_llm
from tocky.utils.models import LLMSpecifier, get_model_info

SYSTEM_PROMPT = """
You are a bot that helps to extract the full table of contents data in a structured format.

{format_instructions}

Notes:
- The label is used for unimportant data like numerals.
- Don't output text in ALL CAPS.

### Examples:

{PROMPT_SAMPLES[no_titles]}

{PROMPT_SAMPLES[nested]}
"""

@dataclass
class AiVisionExtractorOptions:
    model: LLMSpecifier | str = "openai/gpt-4o-mini"
    image_size: int = 2048
    extraction_format: Literal['json', 'markdown'] = 'json'


class AiVisionExtractor(AbstractExtractor[AiVisionExtractorOptions]):
    name = 'ai_vision_extractor'

    def __init__(self):
        super().__init__()
        self.P = AiVisionExtractorOptions()

    @property
    def model(self):
        m = get_model_info(self.P.model)
        assert m
        return m

    def build_system_prompt(self) -> str:
        return build_system_prompt(SYSTEM_PROMPT, self.P.extraction_format, show_input=False)

    def build_images(self, ocaid: str, detector_result: list[int]) -> list[Image.Image]:
        images: list[Image.Image] = []
        for img in get_book_images(ocaid, detector_result, reduce=1):
            max_dimension = max(img.width, img.height)
            if max_dimension > self.P.image_size:
                scale = self.P.image_size / max_dimension
                new_width = int(img.width * scale)
                new_height = int(img.height * scale)
                images.append(img.resize(
                    (new_width, new_height),
                    Image.LANCZOS
                ))
            else:
                images.append(img)
        return images

    def extract(self, ocaid: str, detector_result: list[int]) -> list[TocEntry]:
        self.log_debug(f"Loading and resizing images from {ocaid}...", end="")
        images = self.build_images(ocaid, detector_result)
        self.log_debug(f" ✓")

        self.log_debug(f"Loading OCR...", end="")
        djvu_xml_to_fetch = set(detector_result) - set(self.S.ocr_cache.keys())
        if djvu_xml_to_fetch:
            djvu_url = ocaid_to_djvu_url(ocaid)
            start = min(djvu_xml_to_fetch)
            end = max(djvu_xml_to_fetch)
            for leaf_num, elem in get_djvu_by_leaf_nums(djvu_url, start, end):
                if leaf_num in djvu_xml_to_fetch:
                    self.S.ocr_cache[leaf_num] = etree.tostring(elem, encoding='unicode')
        self.toc_raw_ocr = [self.S.ocr_cache[leaf_num] for leaf_num in detector_result]
        self.toc_flat_ocr = [print_ocr(ocr) for ocr in self.toc_raw_ocr]
        self.log_debug(f" ✓")

        self.log_debug(f"Hitting LLM...", end="")
        completion = self.log_llm_expense(self.model, hit_llm)(
            self.P.model,
            system_prompt=self.build_system_prompt(),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Please extract the table of contents from these images",
                        },
                        *(
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_to_base64(img)}",
                                    "detail": "high",
                                },
                            }
                            for img in images
                        )
                    ],
                },
            ],
        )
        self.log_debug(f" ✓")

        if self.debug:
            self.completion = completion

        assert completion.choices[0].message.content
        assert completion.usage

        toc = process_extracted_output(
            completion.choices[0].message.content,
            self.P.extraction_format,
        )
        self.toc_response = TocResponse(
            toc,
            prompt_tokens=completion.usage.prompt_tokens,
            completion_tokens=completion.usage.completion_tokens,
        )

        return self.toc_response.toc

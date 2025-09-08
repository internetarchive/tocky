from dataclasses import dataclass
from typing import Literal

from tocky.detector.ai_vision_detector import concatenate_and_resize, image_to_base64
from tocky.extractor import AbstractExtractor, TocEntry, TocResponse
from tocky.extractor.formats import build_system_prompt, process_extracted_output
from tocky.utils.ia import get_book_images
from tocky.utils.llm import hit_llm

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
    model: str = "gpt-4o-mini"
    target_height: int = 512
    extraction_format: Literal['json', 'markdown'] = 'json'


class AiVisionExtractor(AbstractExtractor[AiVisionExtractorOptions]):
    name = 'ai_vision_extractor'

    def __init__(self):
        super().__init__()
        self.P = AiVisionExtractorOptions()

    def extract(self, ocaid: str, detector_result: list[int]) -> list[TocEntry]:
        toc_page_image = concatenate_and_resize(list(get_book_images(ocaid, detector_result, reduce=1)), target_height=512)

        system_prompt = build_system_prompt(SYSTEM_PROMPT, self.P.extraction_format)
        completion = hit_llm(
            f"openai/{self.P.model}",
            system_prompt=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Please extract the table of contents from this image.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_to_base64(toc_page_image)}"
                            },
                        },
                    ],
                },
            ],
            # max_tokens=4096,
        )

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

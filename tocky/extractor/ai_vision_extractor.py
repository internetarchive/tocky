from dataclasses import dataclass
import textwrap

from openai import OpenAI
from tocky.detector.ai_vision_detector import concatenate_and_resize, image_to_base64
from tocky.extractor import AbstractExtractor, TocResponse
from tocky.utils import ShareableState
from tocky.utils.ia import get_book_images

SYSTEM_PROMPT = """
You are a bot that helps to extract the full table of contents data in a structured format. The format you will need to output is as follows:

```
* {label (optional)} | {title} | {page number}
```

Notes:
- The label is used for unimportant data like numerals.
- Don't output text in ALL CAPS.

### Examples:

```
* | Preface | ix
* Part 1 | This World | 1
    ** Chapter I | Of the Nature of Flatland | 3
    ** Chapter II | Of the Climate and Houses in Flatland | 5
* Part 2 | Other Worlds | 42
```

```
* | Chapter 1 | 1
* | Chapter 2 | 25
* | Chapter 3 | 38
* | Chapter 4 | 48
```

You can nest when necessary:

```
* A | Technology |
    ** I | Computers | 1
        *** | Hard-drives | 2
        *** | Software | 8
    ** II | Machinery | 11
    ** III | Hardware | 37
* B | Agriculture |
```
"""

@dataclass
class AiVisionExtractorOptions:
    model: str = "gpt-4o-mini"
    target_height: int = 512


class AiVisionExtractor(AbstractExtractor[AiVisionExtractorOptions]):
    name = 'ai_vision_extractor'

    def __init__(self):
        super().__init__()
        self.P = AiVisionExtractorOptions()

    def extract(self, ocaid: str, detector_result: list[int]) -> str:
        toc_page_image = concatenate_and_resize(list(get_book_images(ocaid, detector_result, reduce=1)), target_height=512)

        client = OpenAI()
        completion = client.chat.completions.create(
            model=self.P.model,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
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

        self.toc_response = TocResponse(
            toc=completion.choices[0].message.content,
            prompt_tokens=completion.usage.prompt_tokens,
            completion_tokens=completion.usage.completion_tokens,
        )

        return self.toc_response.toc

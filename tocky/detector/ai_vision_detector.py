import base64
from dataclasses import dataclass
import json
import re
import textwrap
from io import BytesIO

from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont

from tocky.detector import AbstractDetector
from tocky.utils.ia import get_book_images
from tocky.utils.llm import MODEL_PRICES

SYSTEM_PROMPT: str = """
You are a bot that helps in the detection of all table of contents pages in a book.

Notes:
- Make sure to get all the pages, not just the first page of the table of contents
- AVOID things like the copyright page or table of figures/illustrations
- If you cannot detect a table of contents, output an empty array instead of guessing

Please output only JSON of this format: { "toc_pages": [7,8], "notes": "<anything you want to share>" }
"""

@dataclass
class AiVisionDetectorOptions:
    model: str = "gpt-4o-mini"
    max_tokens: int = 200
    image_size: tuple[int, int] = (1024, 512)

class AiVisionDetector(AbstractDetector[AiVisionDetectorOptions]):
    """
    This detector uses multi-modal AI models ability to process images and text together
    to detect table of contents pages in a book.
    """
    name = 'ai_vision_detector'

    def __init__(self):
        super().__init__()
        self.P = AiVisionDetectorOptions()

    @property
    def model(self):
        return MODEL_PRICES[self.P.model]

    def predict_cost(self):
        return self.model.predict_cost([SYSTEM_PROMPT], self.P.max_tokens, [self.P.image_size])

    def detect(self, ocaid: str):
        small_images = list(get_book_images(ocaid, range(0, 28), reduce=3))
        composite_image = place_images_in_grid(
            small_images,
            composite_width=self.P.image_size[0],
            composite_height=self.P.image_size[1],
            image_width=140,
        )

        if self.debug:
            self.small_images = small_images
            self.composite_image = composite_image

        client = OpenAI()
        response = client.chat.completions.create(
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
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_to_base64(composite_image)}",
                                # "detail": "low",
                            }
                        },
                    ],
                }
            ],
            max_tokens=self.P.max_tokens,
        )

        if self.debug:
            self.response = response

        response_str = response.choices[0].message.content
        assert response_str
        json_m = re.search(r'\{[\s\S]*\}', response_str, flags=re.MULTILINE)
        assert json_m

        return json.loads(json_m.group(0))['toc_pages']



def place_images_in_grid(images, composite_width=1024, composite_height=512, image_width=100):
    # Set the larger image height as twice the desired composite height
    larger_image_height = composite_height * 2

    # Calculate the number of images per row and initial image height
    num_images_per_row = composite_width // image_width
    spacing_x = (composite_width % image_width) // (num_images_per_row - 1) if num_images_per_row > 1 else 0
    image_height = min((img.size[1] * image_width) // img.size[0] for img in images)

    # Create a larger composite image with a white background
    larger_composite_image = Image.new('RGB', (composite_width, larger_image_height), (0,0,0))

    # You may need to specify a font file if the default is not acceptable
    font = ImageFont.load_default()

    # Starting position
    x_offset, y_offset = 0, 0

    # Place images in the larger composite image
    for i, img in enumerate(images):
        img_resized = img.resize((image_width, image_height), Image.ANTIALIAS)

        # Create a drawing context to draw on the resized image
        draw_img = ImageDraw.Draw(img_resized)

        # Define the text to draw
        text = str(i)
        text_width, text_height = draw_img.textsize(text, font=font)

        # Calculate position for text, rectangle size and draw a white rectangle behind the text
        text_x, text_y = 5, 5
        rect_x1, rect_y1 = text_x - 2, text_y - 2
        rect_x2, rect_y2 = text_x + text_width + 2, text_y + text_height + 2
        draw_img.rectangle((rect_x1, rect_y1, rect_x2, rect_y2), fill="white")

        # Draw the text over the rectangle
        draw_img.text((text_x, text_y), text, font=font, fill="black")

        # Check if the next image fits in the current row and adjust offsets appropriately
        if x_offset + image_width > composite_width:
            x_offset = 0
            y_offset += image_height + 10  # Add 10 px vertical spacing

        # Paste the image with text into the larger composite
        larger_composite_image.paste(img_resized, (x_offset, y_offset))

        # Update the x_offset for the next image
        x_offset += image_width + spacing_x

    # Finally, crop the larger composite image to the desired final size
    final_composite_image = larger_composite_image.crop((0, 0, composite_width, composite_height))

    return final_composite_image


def image_to_base64(pil_image, format="PNG"):
    # Create an in-memory bytes buffer
    buffer = BytesIO()
    # Save the image to the buffer in the specified format
    pil_image.save(buffer, format=format)
    # Get the raw bytes of the image data from the buffer
    img_bytes = buffer.getvalue()
    # Encode the bytes to base64
    img_base64 = base64.b64encode(img_bytes)
    # Convert bytes to string for easier usage
    img_base64_str = img_base64.decode('utf-8')
    return img_base64_str

def concatenate_and_resize(images, target_height=512):
    # Get the total width of all images combined
    total_width = sum(img.size[0] for img in images)

    # Calculate the height of the tallest image (to set the row height)
    max_height = max(img.size[1] for img in images)

    scale_factor = target_height / max_height
    target_width = int(total_width * scale_factor)

    combined_image = Image.new('RGB', (target_width, target_height))

    # Concatenate images into one big row
    x_offset = 0
    for img in images:
        new_width = int(img.size[0] * scale_factor)
        resized_img = img.resize((new_width, target_height), Image.ANTIALIAS)

        # Paste the resized image into the combined image
        combined_image.paste(resized_img, (x_offset, 0))
        x_offset += new_width

    return combined_image

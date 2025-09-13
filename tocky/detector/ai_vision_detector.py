import base64
from dataclasses import dataclass
import json
import re
from io import BytesIO
from typing import Literal
import math

from PIL import Image, ImageDraw, ImageFont

from tocky.detector import AbstractDetector
from tocky.utils.ia import get_book_images
from tocky.utils.llm import hit_llm
from tocky.utils.models import LLMSpecifier, get_model_info

SYSTEM_PROMPT: str = """
You are a bot that helps in the detection of all table of contents pages in a book.

Notes:
- Make sure to get all the pages, not just the first page of the table of contents
- AVOID things like the copyright page, or table of figures/illustrations, or pages that are blank
- If you cannot detect a table of contents, output an empty array instead of guessing

Please output only JSON of this format: { "toc_pages": [7,8], "notes": "<anything you want to share>" }
"""

@dataclass
class AiVisionDetectorOptions:
    model: LLMSpecifier | str = "openai/gpt-5-nano"
    max_tokens: int = 200
    image_size: tuple[int, int] = (2 * 512, 3 * 512)
    page_width: int = 165

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
        m = get_model_info(self.P.model)
        assert m
        return m

    def build_composite_image(self, ocaid: str, reuse=False) -> Image.Image:
        if self.debug and reuse and hasattr(self, 'small_images'):
            small_images = self.small_images
        else:
            small_images = list(get_book_images(ocaid, range(0, 36), reduce=3))
        composite_image = place_images_in_grid(
            small_images,
            composite_width=self.P.image_size[0],
            composite_height=self.P.image_size[1],
            image_width=self.P.page_width,
            # make_square=True,
            # square_method='crop',
            cut_percent=5.0,
        )

        if self.debug:
            self.small_images = small_images
            self.composite_image = composite_image

        return composite_image

    def detect(self, ocaid: str):
        composite_image = self.build_composite_image(ocaid)
        response = self.log_llm_expense(self.model, hit_llm)(
            self.P.model,
            system_prompt=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_to_base64(composite_image)}",
                                "detail": "high",
                            }
                        },
                    ],
                }
            ],
            # max_tokens=self.P.max_tokens,
        )

        if self.debug:
            self.response = response

        response_str = response.choices[0].message.content
        assert response_str
        json_m = re.search(r'\{[\s\S]*\}', response_str, flags=re.MULTILINE)
        assert json_m

        return json.loads(json_m.group(0))['toc_pages']



def place_images_in_grid(
    images,
    composite_width=1024,
    composite_height=512,
    image_width=100,
    make_square=False,
    square_method: Literal['crop', 'squish', 'proportional_squish']='crop',
    cut_percent: float = 0.0,
):
    # Set the larger image height as twice the desired composite height
    larger_image_height = composite_height * 2

    # Calculate the number of images per row and initial image height
    num_images_per_row = composite_width // image_width
    spacing_x = (composite_width % image_width) // (num_images_per_row - 1) if num_images_per_row > 1 else 0
    # Normalize cut_percent to [0, 99.0] to avoid zero/negative dimensions
    cut_percent = max(0.0, min(99.0, cut_percent))
    cut_ratio = cut_percent / 100.0
    
    # If making images square, the resized height is the same as image_width; otherwise compute
    # the resized height that preserves aspect ratio when width is image_width.
    image_height = image_width if make_square else min((img.size[1] * image_width) // img.size[0] for img in images)

    # Create a larger composite image with a white background
    larger_composite_image = Image.new('RGB', (composite_width, larger_image_height), (0,0,0))

    # You may need to specify a font file if the default is not acceptable
    font = ImageFont.load_default()

    # Starting position
    x_offset, y_offset = 0, 0

    # Place images in the larger composite image
    for i, img in enumerate(images):
        # First, cut margins before any processing
        if cut_percent > 0:
            w, h = img.size
            dx = int(w * cut_ratio / 2.0)
            dy = int(h * cut_ratio / 2.0)
            dx = min(dx, max(0, (w - 1) // 2))
            dy = min(dy, max(0, (h - 1) // 2))
            img = img.crop((dx, dy, w - dx, h - dy))
        # Optionally make images square before resizing/placing.
        if make_square:
            if square_method == 'crop':
                w, h = img.size
                # Determine the side of the square crop: center horizontally, take from top vertically
                side = min(w, h)
                left = (w - side) // 2
                top = 0
                right = left + side
                bottom = top + side
                img_to_place = img.crop((left, top, right, bottom))
                target_size = (image_width, image_width)
            elif square_method == 'squish':  # ignore aspect ratio, just resize to a square
                img_to_place = img
                target_size = (image_width, image_width)
            else:  # 'proportional_squish'
                img_resized = proportional_squish_to_square(img, image_width)
                img_to_place = img_resized
                target_size = (image_width, image_width)
        else:
            img_to_place = img
            target_size = (image_width, image_height)

        img_resized = img_to_place.resize(target_size, Image.ANTIALIAS)

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


def proportional_squish_to_square(img: Image.Image, size: int) -> Image.Image:
    """
    Transform an image into a square of (size x size) where vertical contribution
    of each source row decreases linearly from top (scale=1) to bottom (scale=0).
    Implementation maps each output scanline y to a source row using the inverse
    of the cumulative linear scale function, ensuring an exact fit into `size` height.
    """
    # Ensure we have a compatible mode and dimensions
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    src_w, src_h = img.size
    if src_h <= 0:
        # Fallback: simple squish if something odd happens
        return img.resize((size, size), Image.ANTIALIAS)

    # First, resize horizontally to the target width while keeping original height.
    # We ignore aspect ratio horizontally only; vertical distribution is handled below.
    horiz_resized = img.resize((size, src_h), Image.ANTIALIAS)

    # Prepare the destination image
    dest = Image.new(horiz_resized.mode if horiz_resized.mode in ("RGB", "RGBA") else "RGB", (size, size))

    # For each output scanline y in [0, size-1], find the corresponding source row.
    # Using derived relation: y_norm = 2u - u^2, where u = t/src_h in [0,1].
    # Inverse: u = 1 - sqrt(1 - y_norm), with y_norm = y/size.
    for y in range(size):
        y_norm = y / size
        # Guard against minor floating issues at y=size-1
        y_norm = min(1.0, max(0.0, y_norm))
        u = 1.0 - math.sqrt(1.0 - y_norm) if y_norm < 1.0 else 1.0
        t = u * src_h
        src_row = min(src_h - 1, max(0, int(t)))

        # Extract a single-row slice and paste it at y
        row = horiz_resized.crop((0, src_row, size, src_row + 1))
        dest.paste(row, (0, y))

    return dest


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

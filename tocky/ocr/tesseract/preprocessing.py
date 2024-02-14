import cv2
import numpy as np
from rtree import index
from PIL import Image

from dataclasses import dataclass
from typing import List

from tocky.utils import Rect

# This one is all ChatGPT :grimacing: Should verify
# Calculate the shortest distance between the two rectangles
def shortest_distance(rect1: Rect, rect2: Rect):
    # Calculate the distance between the right edge of rect1 and the left edge of rect2
    dx = max(0, rect2.left - rect1.right, rect1.left - rect2.right)

    # Calculate the distance between the bottom edge of rect1 and the top edge of rect2
    dy = max(0, rect2.top - rect1.bottom, rect1.top - rect2.bottom)

    # Return the Euclidean distance between the two rectangles
    return (dx**2 + dy**2)**0.5

def in_to_px(inches: float, dpi: int) -> float:
  return inches * dpi

def px_to_in(pixels: float, dpi: int) -> float:
  return pixels / dpi

@dataclass
class LeaderDotsParams:
  dpi: int
  # Note these are in inches -- we represent them in inches to try to make this
  # more resilient to changes in DPI
  _max_dot_height = 0.05
  _kernel_size = 0.015
  _dot_isolation_distance = 0.04
  _inpaint_radius = 0.04

  @property
  def max_dot_height(self) -> int: return round(in_to_px(self._max_dot_height, self.dpi))
  @property
  def kernel_size(self) -> int: return round(in_to_px(self._kernel_size, self.dpi))
  @property
  def dot_isolation_distance(self) -> int: return round(in_to_px(self._dot_isolation_distance, self.dpi))
  @property
  def inpaint_radius(self) -> int: return round(in_to_px(self._inpaint_radius, self.dpi))


def remove_leader_dots(img: Image.Image, dpi: int = 300) -> Image.Image:
  P = LeaderDotsParams(dpi)

  # Load your scanned image
  image = np.array(img.convert('RGB'))

  gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

  # Performing OTSU threshold
  ret, thresh1 = cv2.threshold(gray, 0, 255, cv2.THRESH_OTSU | cv2.THRESH_BINARY_INV)

  # Specify structure shape and kernel size.
  # Kernel size increases or decreases the area
  # of the rectangle to be detected.
  # A smaller value like (10, 10) will detect
  # each word instead of a sentence.
  rect_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (P.kernel_size, P.kernel_size))

  # Applying dilation on the threshold image
  dilation = cv2.dilate(thresh1, rect_kernel, iterations = 1)

  # Finding contours
  contours, hierarchy = cv2.findContours(dilation, cv2.RETR_EXTERNAL,
                                                  cv2.CHAIN_APPROX_NONE)

  # Create an rtree index
  rect_idx = index.Index(properties=index.Property())
  contour_rects: List[Rect] = []

  # Insert bounding boxes of contours into the R-tree index
  for i, contour in enumerate(contours):
      rect = Rect.from_xywh(cv2.boundingRect(contour))
      contour_rects.append(rect)
      rect_idx.insert(i, rect.to_ltrb())

  # Creating a copy of image
  # im2 = image.copy()
  mask = np.zeros_like(image, dtype=np.uint8)
  mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
  mask = mask.astype(np.uint8)

  for i, rect in enumerate(contour_rects):
      # Drawing a rectangle on copied image
      if rect.height < P.max_dot_height:
        closest_rect_indices = [
          result
          for result in rect_idx.nearest(rect.to_ltrb(), 7)
          if result != i
        ]
        closest_rects = [contour_rects[i] for i in closest_rect_indices]
        closest_rect_dist = closest_rects[0]
        closest_dist = shortest_distance(closest_rects[0], rect)
        erase = (
            (
                (closest_dist > P.dot_isolation_distance) and
              len([r for r in closest_rects if r.height < P.max_dot_height]) >= 2
            ) or shortest_distance(closest_rects[0], rect) >= 25
        )
        if erase:
          # cv2.rectangle(im2, (rect.x, rect.y), (rect.right, rect.bottom), (255, 255, 255), thickness=cv2.FILLED)
          cv2.rectangle(mask, (rect.x, rect.y), (rect.right, rect.bottom), (255, 255, 255), thickness=cv2.FILLED)

  reference_area = cv2.ximgproc.guidedFilter(image, mask, radius=P.inpaint_radius, eps=1.0)
  result = cv2.inpaint(image, mask, inpaintRadius=P.inpaint_radius, flags=cv2.INPAINT_TELEA)

  return Image.fromarray(result)

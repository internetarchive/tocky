from dataclasses import dataclass
import re
from lxml import etree
from PIL import Image

@dataclass
class PageScan:
  uri: str
  image: Image.Image
  dpi: int
  lang: str

  @property
  def width(self) -> int:
    return self.image.width
  
  @property
  def height(self) -> int:
    return self.image.height

  def preview(self, width=300) -> Image.Image:
    return self.image.resize((width, int(width * self.image.height / self.image.width)))


@dataclass
class Rect:
  x: int
  y: int
  width: int
  height: int
  left: int
  right: int
  bottom: int
  top: int

  @staticmethod
  def from_xywh(rect: tuple) -> 'Rect':
    x, y, w, h = rect
    return Rect(
        x=x,
        y=y,
        width=w,
        height=h,
        left=x,
        right=x + w,
        bottom=y + h,
        top=y,
    )

  @staticmethod
  def from_ltrb(rect: tuple) -> 'Rect':
    l, t, r, b = rect
    return Rect(
        x=l,
        y=t,
        width=r - l,
        height=b - t,
        left=l,
        right=r,
        bottom=b,
        top=t,
    )

  @staticmethod
  def from_cw_points(points: list[list[int]]) -> 'Rect':
    # Points can be rotated
    l = min(p[0] for p in points)
    t = min(p[1] for p in points)
    r = max(p[0] for p in points)
    b = max(p[1] for p in points)
    return Rect.from_ltrb((l, t, r, b))

  def to_ltrb(self) -> tuple:
    return (self.left, self.top, self.right, self.bottom)

def pretty_print_xml(root: etree._Element | str) -> str:
  if isinstance(root, str):
    root = etree.fromstring(root)

  import xml.dom.minidom
  result = xml.dom.minidom.parseString(etree.tostring(root)).toprettyxml(indent='  ')
  return strip_newlines(result)

def strip_newlines(text: str) -> str:
  result = re.sub(r'^\s+$', '', text, flags=re.MULTILINE)
  result = re.sub(r'\n+', '\n', result)
  return result

def avg_ocr_conf(el: etree._Element) -> float:
  conf_sum = 0
  conf_count = 0
  for word in el.findall('.//WORD'):
    if word.xpath('./@x-confidence'):
      conf_sum += float(word.xpath('./@x-confidence')[0])
      conf_count += 1
  if conf_count:
    return conf_sum / conf_count
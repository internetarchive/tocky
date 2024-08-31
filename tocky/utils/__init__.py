from collections.abc import Callable
from dataclasses import dataclass, field
import functools
import re
from time import time
from traceback import TracebackException
from typing import Generic, Literal, TypeVar, cast
from lxml import etree
from PIL import Image


@dataclass
class ShareableState:
  """
  Shareable state between detector runs or between detectors/extractors
  """
  ocr_cache: dict[int, str] = field(default_factory=dict)
  """Map of leaf number to OCR text (djvu xml format)"""


T = TypeVar('T')


@dataclass
class ResultStatSuccess(Generic[T]):
    success: Literal[True]
    time: float
    result: T
    error: None = None
    traceback: None = None

    def to_dict(self):
        return {
            'success': self.success,
            'time': self.time,
            'result': self.result,
        }

@dataclass
class ResultStatError:
    success: Literal[False]
    time: float
    result: None
    error: Exception
    
    @property
    def traceback(self) -> str:
        return '\n'.join(TracebackException.from_exception(self.error).format())

    def to_dict(self):
        return {
            'success': self.success,
            'time': self.time,
            'result': None,
            'error': str(self.error),
            'traceback': self.traceback,
        }
ResultStat = ResultStatSuccess[T] | ResultStatError

def run_with_result_stats(func: Callable[[], T]) -> ResultStat[T]:
    start = time()
    result = None
    try:
        result = func()
        error = None
    except Exception as e:
        error = e
    finally:
        end = time()
        dur = end - start
        if error is None:
            return ResultStatSuccess(
                success=True,
                time=dur,
                result=cast(T, result),
                error=None,
                traceback=None,
            )
        else:
            return ResultStatError(
                success=False,
                time=dur,
                result=None,
                error=error,
            )


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


@functools.cache
def get_git_sha() -> str | None:
  import subprocess

  try:
    return subprocess.check_output(['git', 'rev-parse', 'HEAD']).strip().decode('utf-8')
  except subprocess.CalledProcessError:
    return None

@functools.cache
def get_tocky_version() -> str:
  from importlib.metadata import version, PackageNotFoundError
  try:
    tocky_version = version('tocky')
  except PackageNotFoundError:
    tocky_version = 'local'

  if git_sha := get_git_sha():
    return f'{tocky_version}+{git_sha[:8]}'
  else:
    return tocky_version

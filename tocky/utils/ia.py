from collections.abc import Iterable, Iterator
import functools
from io import BytesIO
import itertools
import re
import sys
from typing import Literal, TypedDict, cast
from internetarchive import get_session
from PIL import Image
from lxml import etree
import pycountry
from requests import HTTPError
import concurrent.futures

from tocky.utils import PageScan

ia_session = get_session()

class IaMetadata(TypedDict):
  identifier: str
  ppi: str
  language: str
  """Usually 3 letter MARC code"""
  title: str
  imagecount: str

class IaFileMetadata(TypedDict):
  name: str
  source: Literal['derivative', 'original', 'metadata']
  format: str
  mtime: str
  size: str
  md5: str
  filecount: str


class IaFullMetadata(TypedDict):
  metadata: IaMetadata
  files: list[IaFileMetadata]


@functools.cache
def get_ia_metadata(ocaid: str) -> IaFullMetadata:
  return ia_session.get(f"https://archive.org/metadata/{ocaid}").json()

def get_page_image(
  ocaid: str,
  leaf_num: int,
  ext='jpg',
  reduce=2,
  quality=80,
  jp2_zip=None,
) -> Image.Image:
  jp2_zip = jp2_zip or f"{ocaid}_jp2.zip"
  file_prefix = jp2_zip.replace('_jp2.zip', '')
  url = f"https://archive.org/download/{ocaid}/{jp2_zip}/{jp2_zip.replace('.zip', '')}%2F{file_prefix}_{leaf_num:04}.jp2"
  img = ia_session.get(url, params={
      'ext': ext,
      'reduce': str(reduce),
      'quality': str(quality),
  })

  img.raise_for_status()

  return Image.open(BytesIO(img.content))

def get_page_scan(
  ocaid: str,
  leaf_num: int,
  ext = 'jpg',
  reduce = 0,
  quality = 100,
  image: Image.Image | None = None
) -> PageScan:
  """
  :param ocaid: The identifier of the item on archive.org
  :param leaf_num: The leaf number of the page to fetch
  :param image: An optional PIL Image object to use instead of fetching the image from the internet
  """
  full_metadata = get_ia_metadata(ocaid)

  if not image:
    jp2_zip = get_main_jp2_zip(full_metadata)
    image = get_page_image(ocaid, leaf_num, ext=ext, reduce=reduce, quality=quality, jp2_zip=jp2_zip)

  return PageScan(
    uri=f'https://archive.org/details/{ocaid}#page/leaf{leaf_num}',
    image=image,
    dpi=int(full_metadata['metadata']['ppi']),
    lang=ia_language_to_iso639_2_code(full_metadata['metadata']['language']) or 'eng',
  )


def get_main_jp2_zip(ocaid_or_metadata: str | IaFullMetadata) -> str:
  if isinstance(ocaid_or_metadata, str):
    full_metadata = get_ia_metadata(ocaid_or_metadata)
  else:
    full_metadata = ocaid_or_metadata

  all_jp2_zips = list(
    file
    for file in full_metadata['files']
    if file['name'].endswith('_jp2.zip') and not file['name'].endswith('_raw_jp2.zip')
  )
  assert all_jp2_zips, "No jp2 files found"
  assert len(all_jp2_zips) == 1, f"Multiple jp2 files found {[f['name'] for f in all_jp2_zips]}"
  jp2_zip = all_jp2_zips[0]
  return jp2_zip['name']


def get_book_images(
  ocaid: str,
  leaf_nums: Iterable[int],
  reduce = 3,
) -> Iterator[Image.Image]:
  jp2_zip = get_main_jp2_zip(ocaid)
  def get_image(leaf_num: int):
    # try:
      return get_page_image(ocaid, leaf_num, reduce=reduce, jp2_zip=jp2_zip)
    # except HTTPError as e:
    #   # Return an empty image of size 100x300
    #   return Image.new('RGB', (100, 300))
    
  with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    return executor.map(get_image, leaf_nums)

def ia_language_to_iso639_2_code(lang: str) -> str | None:
  if len(lang) == 3:
    return lang
  else:
    language = pycountry.languages.get(name=lang)
    if language:
      return language.alpha_3
    else:
      return None

def extract_page_index(page_filename: str) -> int:
  return int(re.search(r'(?:_)(\d+)(?:\.djvu)', page_filename).group(1))

def ocaid_to_djvu_url(ocaid: str) -> str:
  get_ia_metadata(ocaid)
  return f"https://archive.org/download/{ocaid}/{ocaid}_djvu.xml"

def get_djvu_pages(djvu_url: str, start: int=0, end: int=sys.maxsize):
    response = ia_session.get(djvu_url, stream=True)

    if response.status_code != 200:
        print("Error: Unable to fetch the DJVU file.")
        return

    response.raw.decode_content = True
    for _, elem in itertools.islice(etree.iterparse(response.raw, events=("end",), tag="OBJECT"), start, end):
      page_name = cast(str, elem.xpath(".//PARAM[@name='PAGE']/@value")[0])
      yield page_name, cast(etree._Element, elem)
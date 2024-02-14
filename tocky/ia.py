import functools
from io import BytesIO
import itertools
import re
import sys
from typing import cast
from internetarchive import get_session
from PIL import Image
from lxml import etree
import pycountry

from tocky.utils import PageScan

ia_session = get_session()

@functools.cache
def get_ia_metadata(ocaid: str) -> dict:
  return ia_session.get(f"https://archive.org/metadata/{ocaid}/metadata").json()['result']

def get_page_scan(ocaid: str, leaf_num: int, image: Image.Image | None = None) -> PageScan:
  if not image:
    resp = ia_session.get(f"https://archive.org/download/{ocaid}/{ocaid}_jp2.zip/{ocaid}_jp2%2F{ocaid}_{leaf_num:04}.jp2", params={
      'ext': 'jpg',
      'reduce': '0',
      'quality': '100',
    })
    resp.raise_for_status()
    image = Image.open(BytesIO(resp.content))

  metadata = get_ia_metadata(ocaid)

  return PageScan(
    uri=f'https://archive.org/details/{ocaid}#page/leaf{leaf_num}',
    image=image,
    dpi=int(metadata['ppi']),
    lang=ia_language_to_iso639_2_code(metadata['language']) or 'eng',
  )

def ia_language_to_iso639_2_code(lang: str) -> str | None:
  if len(lang) == 3:
    return lang
  else:
    return pycountry.languages.get(name=lang)

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
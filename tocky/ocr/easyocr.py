import easyocr
from dataclasses import dataclass
from lxml import etree
from rtree import index

from tocky.utils import PageScan, Rect

# this needs to run only once to load the model into memory
reader = easyocr.Reader(['en'])

def y_overlap(rect1: Rect, rect2: Rect) -> int:
    """
    <WORD coords="169,1633,418,1568" x-confidence="99.19">Susceptance</WORD>
    near: <WORD coords="64,1618,140,1514" x-confidence="99.03">1-6</WORD>
    (1568, 1633) -- (1514, 1618)
            (1568, 1618)

             [1568           1633]
    [1514           1618]
    """
    intersection_top = max(rect1.top, rect2.top)
    intersection_bottom = min(rect1.bottom, rect2.bottom)

    return max(0, intersection_bottom - intersection_top)

@dataclass
class OCRWord:
  index: int
  text: str
  rect: Rect
  conf: float  # Number between 0 and 1

  def to_xml(self):
    # <WORD coords="241,509,757,421" x-confidence="96">Psychological</WORD>
    el = etree.Element('WORD')
    el.set('coords', f'{round(self.rect.left)},{round(self.rect.bottom)},{round(self.rect.right)},{round(self.rect.top)}')
    el.set('x-confidence', f'{(self.conf * 100):.2f}')
    el.text = self.text
    return el

def index_words(words: list[OCRWord]) -> index.Index:
  rect_idx = index.Index()

  for word in words:
    rect_idx.insert(word.index, word.rect.to_ltrb())

  return rect_idx


def group_into_lines(words: list[OCRWord], max_width: int) -> list[list[OCRWord]]:
  rect_idx = index_words(words)

  word_i_to_line_i = {}
  max_line_id = 0
  for word in words:
    # print(word.text)
    mid_y = word.rect.top + (word.rect.bottom - word.rect.top) / 2
    for nearby_word_i in rect_idx.nearest((0, mid_y, max_width, mid_y), 5):
      if nearby_word_i == word.index:
        continue
      nearby_word = words[nearby_word_i]
      overlap = y_overlap(word.rect, nearby_word.rect) / word.rect.height
      # print(f'    near "{nearby_word.text}" ({overlap=})')
      if overlap > 0.35 and nearby_word.index in word_i_to_line_i:
        # print(repr(word.text), '->', word_i_to_line_i[nearby_word.index])
        word_i_to_line_i[word.index] = word_i_to_line_i[nearby_word.index]
        break
    else:
      # print('    ', repr(word.text), '->', max_line_id)
      max_line_id += 1
      word_i_to_line_i[word.index] = max_line_id

  lines = [[] for _ in range(max_line_id+1)]
  for word_id, line_id in word_i_to_line_i.items():
    lines[line_id].append(words[word_id])
  for line in lines:
    line.sort(key=lambda word: (word.rect.left // 50, word.rect.top))
  return lines


def ocr_djvu_page_easyocr(page_scan: PageScan) -> str:
  print('ocr_djvu_page_easyocr', page_scan.uri)
  # return reader.readtext(img)
  words = [
      OCRWord(index=i, text=text, rect=Rect.from_cw_points(cw_points), conf=conf)
      for i, (cw_points, text, conf) in enumerate(
          (cw_points, text, conf)
          for (cw_points, text, conf) in reader.readtext(page_scan.image)
          if text and not (len(text) <= 2 and conf < 0.1)
      )
  ]

  par_el = etree.Element('PARAGRAPH')
  for line in group_into_lines(words, page_scan.image.width):
    line_el = etree.Element('LINE')
    for word in line:
      line_el.append(word.to_xml())
    par_el.append(line_el)
  return (
    f'<OBJECT type="image/x.djvu" width="{page_scan.width}" height="{page_scan.height}">\n'
      f'<PARAM name="DPI" value="{page_scan.dpi}"/>\n'
      '<HIDDENTEXT x-re-ocrd="true">'
        '<PAGECOLUMN>'
          '<REGION>'
            + etree.tostring(par_el, encoding='utf-8').decode('utf-8') +
          '</REGION>'
        '</PAGECOLUMN>'
    '</HIDDENTEXT>'
  '</OBJECT>'
  )
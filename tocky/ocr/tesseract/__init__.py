import pytesseract
from PIL import Image
from io import StringIO
from lxml import etree
import pandas as pd
import csv

from tocky.ocr.tesseract.preprocessing import remove_leader_dots
from tocky.utils import PageScan

def ocr_image(img: Image.Image, psm: int, dpi: int, lang: str = 'eng'):
  ocr_tsv_data = pytesseract.image_to_data(remove_leader_dots(img), config=f'--psm {psm} --dpi {dpi} -l {lang}')
  df = pd.read_csv(StringIO(ocr_tsv_data), sep='\t', quoting=csv.QUOTE_NONE)
  df = df[
      (~df.text.isna())
      & (~df['text'].isin(['', *' |{}\\_=—']))
      & (df['width'] > 0)
  ]
  # Round to make displaying lines/etc more easily aligned
  # df['left'] = df['left'].apply(lambda n: 10 * (n // 10))
  # df['top'] = df['top'].apply(lambda n: 10 * (n // 10))
  return df.reset_index()


def ocr_djvu_page_tesseract(scanned_page: PageScan) -> str:
  """
  OCR a page of a djvu using tesseract and return the result as a HIDDENTEXT DjVu XML string
  """
  df = ocr_image(scanned_page.image, psm=3, dpi=scanned_page.dpi, lang=scanned_page.lang)

  ## Find the closest rect in the --psm 4 table that possible contains the rect
  # low_conf_words = df[df['conf'] < 90]
  # ocr_psm_4 = ocr_image(img, psm=4)
  # for index, lc_row in low_conf_words.iterrows():
  #   ocr_psm_4['distance'] = ocr_psm_4.apply(lambda row: abs(row.left - lc_row.left) + abs(row.top - lc_row.top), axis=1)
  #   best = ocr_psm_4.sort_values('distance').iloc[0]
  #   if best.distance < 5 and best.text != lc_row.text and best.conf > lc_row.conf:
  #     #print(index, (lc_row.text, lc_row.conf), '→', (best.text, best.conf), best.distance)

  #     df.loc[index, 'text'] = best.text
  #     df.loc[index, 'conf'] = best.conf
  #     df.loc[index, 'left'] = best.left
  #     df.loc[index, 'top'] = best.top
  #     df.loc[index, 'width'] = best.width
  #     df.loc[index, 'height'] = best.height

  lines = []
  for _, group in df.groupby(['block_num', 'par_num', 'line_num']):
    line_el = etree.Element('LINE')
    for index, row in group.iterrows():
      # <WORD coords="241,509,757,421" x-confidence="96">Psychological</WORD>
      word_el = etree.Element('WORD')
      word_el.set('coords', f'{row.left},{row.top + row.height},{row.left + row.width},{row.top}')
      word_el.set('x-confidence', str(row.conf))
      word_el.text = row.text
      line_el.append(word_el)
    lines.append(etree.tostring(line_el, encoding='utf-8').decode('utf-8'))
  return (
    f'<OBJECT type="image/x.djvu" width="{scanned_page.width}" height="{scanned_page.height}">\n'
      f'<PARAM name="DPI" value="{scanned_page.dpi}"/>\n'
      '<HIDDENTEXT x-re-ocrd="true">'
        '<PAGECOLUMN>'
          '<REGION>'
            '<PARAGRAPH>\n' + '\n'.join(lines) + '\n</PARAGRAPH>'
          '</REGION>'
        '</PAGECOLUMN>'
    '</HIDDENTEXT>'
  '</OBJECT>'
  )
  


from typing import Literal
from tocky.utils import PageScan


def ocr_djvu_page(page_scan: PageScan, engine: Literal['easyocr', 'tesseract', 'azure'] = 'easyocr') -> str:
  if engine == 'easyocr':
    from tocky.ocr.easyocr import ocr_djvu_page_easyocr
    return ocr_djvu_page_easyocr(page_scan)
  elif engine == 'tesseract':
    from tocky.ocr.tesseract import ocr_djvu_page_tesseract
    return ocr_djvu_page_tesseract(page_scan)
  elif engine == 'azure':
    from tocky.ocr.azure import ocr_djvu_page_azure
    return ocr_djvu_page_azure(page_scan)
  else:
    raise ValueError(f'Unknown OCR engine {engine}')

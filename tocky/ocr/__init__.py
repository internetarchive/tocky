from typing import Literal
from tocky.env import get_env
from tocky.utils import PageScan
import importlib.util

def get_supported_engines() -> list[dict]:
  azure_disabled = not get_env().AZURE_ENDPOINT or not get_env().AZURE_SUBSCRIPTION_KEY
  azure_result = {
    'name': 'azure',
    'disabled': azure_disabled,
  }
  if azure_disabled:
    azure_result['reason'] = 'Missing authentication credentials'
  
  # For easyocr, check if the package is installed, but don't import it
  # because it's slow to import.
  easyocr_disabled = importlib.util.find_spec('easyocr') is None
  easyocr_result = {
    'name': 'easyocr',
    'disabled': easyocr_disabled,
  }
  if easyocr_disabled:
    easyocr_result['reason'] = 'Not installed'
  
  # Similarly for tesseract
  tesseract_disabled = importlib.util.find_spec('pytesseract') is None
  tesseract_result = {
    'name': 'tesseract',
    'disabled': tesseract_disabled,
  }
  if tesseract_disabled:
    tesseract_result['reason'] = 'Not installed'
  
  return [azure_result, easyocr_result, tesseract_result]
  


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

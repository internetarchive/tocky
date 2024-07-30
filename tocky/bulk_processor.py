from dataclasses import dataclass, field
import re
from typing import TypedDict
import tiktoken
import json
import traceback
import os
import requests
from lxml import etree

from tocky.detector import extract_toc_pages
from tocky.extractor import extract_structured_toc
from tocky.ocr.printer import print_ocr
from tocky.utils.ia import extract_page_index, get_ia_metadata, get_page_scan
from tocky.ocr import ocr_djvu_page
from tocky.utils import avg_ocr_conf
from tocky.validator import validate_extracted_toc

@dataclass
class ItemProcessingState:
  ocaid: str
  status: str = ''
  toc_raw_ocr: list[str] = field(default_factory=list)
  detected_toc: list[tuple[str, str]] = field(default_factory=list)
  toc_ocr: str = ''
  structured_toc: str = ''
  error: Exception | None = None
  prompt_tokens: int = 0
  completion_tokens: int = 0


def process_ol_book(ol_record: dict) -> ItemProcessingState:
  state = ItemProcessingState(ocaid=ol_record['ocaid'])
  ol_toc = ol_record.get('table_of_contents')
  if ol_toc:
    toc_missing_pagenums = not any(chapter.get('pagenum') for chapter in ol_toc)
    if ol_toc and not toc_missing_pagenums:
      state.status = 'Already has good TOC'
      return state

  def redo_ocr(djvu_xml: str, page_name: str) -> str:
    root = etree.fromstring(djvu_xml)
    if root.xpath('.//HIDDENTEXT/@x-re-ocrd') == ['true']:
      return djvu_xml

    ocaid = page_name.rsplit('_', 1)[0]
    leaf_num = extract_page_index(page_name)
    new_ocr = ocr_djvu_page(get_page_scan(ocaid, leaf_num))
    new_ocr_el = etree.fromstring(new_ocr).find('.//HIDDENTEXT')
    if (avg_ocr_conf(new_ocr_el) or 100) > (avg_ocr_conf(root.find('.//HIDDENTEXT')) or 0):
      root.replace(root.find('.//HIDDENTEXT'), new_ocr_el)

    return etree.tostring(root, encoding='unicode')

  try:
    state.detected_toc = list(extract_toc_pages(state.ocaid))
  except Exception as e:
    state.status = 'Errored'
    state.error = e
    return state

  if not state.detected_toc:
    state.status = 'No TOC detected'
  else:
    try:
      state.toc_raw_ocr = [
          print_ocr(redo_ocr(djvu_xml, page_name))
          for (page_name, djvu_xml) in state.detected_toc
      ]
    except Exception as e:
      state.status = 'Errored'
      state.error = e

    if re.search(r'([A-Za-z]{25,}|\beee+\b)', '\n'.join(state.toc_raw_ocr), flags=re.MULTILINE):
      state.status = 'Bad OCR on TOC'
    else:
      chunks = ['']
      for page_ocr in state.toc_raw_ocr:
        extended_chunk = chunks[-1] + '\n' + page_ocr
        if len(tiktoken.encoding_for_model("gpt-3.5-turbo").encode(extended_chunk)) > 1000:
          chunks.append(page_ocr)
        else:
          chunks[-1] += '\n' + page_ocr
      try:
        book_title = get_ia_metadata(state.ocaid)['metadata']['title']
        for chunk in chunks:
          toc_response = extract_structured_toc(chunk, book_title, prev_toc=state.structured_toc)
          state.structured_toc += '\n' + toc_response.toc.strip().strip('`').strip()
          state.prompt_tokens += toc_response.prompt_tokens
          state.completion_tokens += toc_response.completion_tokens
        state.status = 'TOC Extracted'
      except Exception as e:
        state.status = 'Errored'
        state.error = e
      if state.structured_toc:
        total_pages = int(get_ia_metadata(state.ocaid)['metadata']['imagecount'])
        validation = validate_extracted_toc(state.structured_toc, total_pages)
        if validation != 'Valid':
          state.status = f'TOC Validation: {validation}'

  return state

def push_to_toc_queue(record: dict):
  return requests.put(
      'https://testing.openlibrary.org/tocky/push',
      headers={
          'X-API-KEY': os.environ['TOC_QUEUE_DB_PASSWORD'],
          'Content-Type': 'application/json',
      },
      data=json.dumps(record)
  )


class IaSearchParams(TypedDict):
  q: str
  sort: str


def process_all(ia_params: IaSearchParams, rows=10, page=1, ia_overrides=None):
  ia_overrides = ia_overrides or {}
  ia_records = requests.get('https://archive.org/advancedsearch.php', params={
    **ia_params,
    'fl': 'identifier,openlibrary_edition',
    'rows': rows,
    'page': page,
    'output': 'json',
  }).json()['response']['docs']

  for ia_record in ia_records:
    if ia_record['identifier'] in ia_overrides:
      ia_record |= ia_overrides[ia_record['identifier']]

  ol_records_by_key = requests.get('http://openlibrary.org/api/get_many', params={
      'keys': json.dumps([
          f'/books/{metadata["openlibrary_edition"]}'
          for metadata in ia_records
      ])
  }).json()['result']

  for ia_record in ia_records:
    ol_record = ol_records_by_key[f'/books/{ia_record["openlibrary_edition"]}']
    if 'ocaid' not in ol_record:
      ol_record['ocaid'] = ia_record['identifier']

  import concurrent.futures
  all_results = []
  with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    for result in executor.map(process_ol_book, ol_records_by_key.values()):
      print(f'[{result.status}] {result.ocaid}')
      push_to_toc_queue({
          'code_version': 'v2.E.1',
          'ocaid': result.ocaid,
          'status': result.status,
          'prompt_tokens': result.prompt_tokens,
          'completion_tokens': result.completion_tokens,
          'error': str(result.error) if result.error else None,
          'toc_raw_ocr': result.toc_raw_ocr,
          'structured_toc': result.structured_toc,
          'detected_toc': [extract_page_index(p[0]) for p in result.detected_toc],
      })
      if result.error:
        print(traceback.print_exception(result.error))
      all_results.append(result)
  return all_results

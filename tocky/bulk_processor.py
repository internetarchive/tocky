from dataclasses import dataclass, field
import re
from typing import Literal, TypedDict
import json
import traceback
import os
import requests


from tocky.detector import AbstractDetector
from tocky.detector.ocr_detector import OcrDetector
from tocky.extractor.ai_extractor import AiExtractor, TocResponse
from tocky.utils.ia import bulk_ia_to_ol, get_ia_metadata
from tocky.utils import ResultStat, run_with_result_stats
from tocky.validator import validate_extracted_toc

TockyItemState = Literal[
  "To Detect",
  "Detecting",
  "To Extract",
  "Extracting",
  "To Review",
  "Reviewing",
  "Done",
]

@dataclass
class ItemProcessingState:
  ocaid: str
  state: TockyItemState = 'To Detect'
  status: str = ''

  detector_result: ResultStat[list[int]] | None = None
  extractor_result: ResultStat[TocResponse] | None = None

  toc_raw_ocr: list[str] = field(default_factory=list)
  detected_toc: list[tuple[str, str]] = field(default_factory=list)
  toc_ocr: str = ''
  structured_toc: str = ''
  error: Exception | None = None
  prompt_tokens: int = 0
  completion_tokens: int = 0


def process_ol_book(
  ol_record: dict, 
  detector: AbstractDetector,
  extractor: AiExtractor,
) -> ItemProcessingState:
  state = ItemProcessingState(ocaid=ol_record['ocaid'])
  ol_toc = ol_record.get('table_of_contents')
  if ol_toc:
    toc_missing_pagenums = not any(chapter.get('pagenum') for chapter in ol_toc)
    if ol_toc and not toc_missing_pagenums:
      state.status = 'Already has good TOC'
      return state
  
  return process_ia_book(state.ocaid, detector, extractor)


def process_ia_book(
  ocaid: str,
  detector: AbstractDetector,
  extractor: AiExtractor,
) -> ItemProcessingState:
  state = ItemProcessingState(ocaid=ocaid)
  state.state = 'Detecting'
  state.detector_result = run_with_result_stats(lambda: detector.detect(state.ocaid))

  if state.detector_result.error is not None:
    state.status = 'Errored'
    state.error = state.detector_result.error
    return state

  if not state.detector_result.result:
    state.status = 'No TOC detected'
  else:
    state.state = 'Extracting'
    state.extractor_result = run_with_result_stats(lambda: extractor.extract(state.ocaid, state.detector_result.result))

    if hasattr(extractor, 'toc_raw_ocr'):
      state.toc_raw_ocr = extractor.toc_raw_ocr

    if state.extractor_result.error is not None:
      state.status = 'Errored'
      state.error = state.extractor_result.error
      return state
  

    state.structured_toc = state.extractor_result.result.toc
    state.prompt_tokens = state.extractor_result.result.prompt_tokens
    state.completion_tokens = state.extractor_result.result.completion_tokens
    state.status = 'TOC Extracted'
    state.state = 'To Review'
    
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

  ol_records_by_key = bulk_ia_to_ol(ia_records)

  import concurrent.futures
  all_results = []

  def run_pipeline(ol_record: dict):
    detector = OcrDetector()
    extractor = AiExtractor()
    return process_ol_book(ol_record, detector, extractor)

  with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    for result in executor.map(run_pipeline, ol_records_by_key.values()):
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
          'detected_toc': result.detector_result.result if result.detector_result else None,
          'detector_result': result.detector_result.to_dict() if result.detector_result else None,
          'extractor_result': result.extractor_result.to_dict() if result.extractor_result else None,
      })
      if result.error:
        print(traceback.print_exception(result.error))
      all_results.append(result)
  return all_results

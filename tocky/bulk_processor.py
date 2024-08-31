from dataclasses import dataclass, field
import dataclasses
from typing import Literal, TypedDict
import json
import traceback
import requests


from tocky import DETECTERS_BY_NAME, EXTRACTORS_BY_NAME
from tocky.detector import AbstractDetector
from tocky.detector.ocr_detector import OcrDetector
from tocky.env import get_env
from tocky.extractor import AbstractExtractor, TocEntry
from tocky.extractor.ai_extractor import AiExtractor
from tocky.utils.ia import bulk_ia_to_ol, get_ia_metadata
from tocky.utils import ResultStat, get_git_sha, get_tocky_version, run_with_result_stats
from tocky.validator import validate_extracted_toc

TockyItemState = Literal[
  "To Detect",
  "Detecting",
  "To Extract",
  "Extracting",
  "To Review",
  "Reviewing",
  "Done",
  "Errored",
]


# Keep in sync with list.html
ExtractionStatus = Literal[
  "",
  "TOC Extracted",
  "No TOC detected",
  "Errored",
  "Already has good TOC",
  "TOC Validation: Unparseable TOC",
  "TOC Validation: Label/Title Too Long",
  "TOC Validation: No Numbers",
  "TOC Validation: Not Enough Numbers",
  "TOC Validation: Too Few Lines With Numbers",
  "TOC Validation: Starts Too High",
  "TOC Validation: End Too Low",
]

@dataclass
class ItemProcessingState:
  ocaid: str
  detector: AbstractDetector
  extractor: AbstractExtractor

  detector_result: ResultStat[list[int]] | None = None
  extractor_result: ResultStat[list[TocEntry]] | None = None

  state: TockyItemState = 'To Detect'
  status: ExtractionStatus = ''
  toc_raw_ocr: list[str] | None = None
  detected_toc: list[tuple[str, str]] = field(default_factory=list)
  structured_toc: list[TocEntry] | None = None
  error: Exception | None = None
  prompt_tokens: int = 0
  completion_tokens: int = 0

  def to_response_dict(self):
    result = {
        'tocky_version': get_tocky_version(),
        'success': all(
            result and result.success
            for result in [self.detector_result, self.extractor_result]
        ),
        'input_book': {
          'type': 'ia_book',
          'ia_id': self.ocaid,
        },
        'detector': {
            'type': self.detector.name,
            'options': self.detector.P.__dict__,
            'results': self.detector_result.to_dict() if self.detector_result else None,
        },
        'extractor': {
            'type': self.extractor.name,
            'options': self.extractor.P.__dict__,
            'results': self.extractor_result.to_dict() if self.extractor_result else None,
        },
    }

    # Convert TocEntry to dict extractor result
    if self.extractor_result and self.extractor_result.result is not None:
      result['extractor']['results']['result'] = [
          entry.to_dict()
          for entry in self.extractor_result.result
      ]

    return result

  def to_db_dict(self):
    return {
      'state': self.state,
      'status': self.status,

      **self.to_response_dict(),

      # Legacy?
      'code_version': 'v2.E.1',
      'ocaid': self.ocaid,
      'prompt_tokens': self.prompt_tokens,
      'completion_tokens': self.completion_tokens,
      'error': str(self.error) if self.error else None,
      'toc_raw_ocr': self.toc_raw_ocr,
      'structured_toc': [entry.to_dict() for entry in self.structured_toc] if self.structured_toc is not None else None,
      'detected_toc': self.detector_result.result if self.detector_result else None,
  }


def process_ol_book(
  ol_record: dict, 
  detector: AbstractDetector,
  extractor: AbstractExtractor,
) -> ItemProcessingState:
  if ol_toc := ol_record.get('table_of_contents'):
    toc_missing_pagenums = not any(chapter.get('pagenum') for chapter in ol_toc)
    if not toc_missing_pagenums:
      return ItemProcessingState(
        ocaid=ol_record['ocaid'],
        detector=detector,
        extractor=extractor,
        state='Done',
        status='Already has good TOC'
      )
  
  return process_ia_book(ol_record['ocaid'], detector, extractor)


def process_ia_book(
  ocaid: str,
  detector: AbstractDetector,
  extractor: AbstractExtractor,
  push: bool = False,
) -> ItemProcessingState:
  state = ItemProcessingState(ocaid=ocaid, detector=detector, extractor=extractor)
  toc_queue_id = 0
  if push:
    toc_queue_id = push_to_toc_queue(state.to_db_dict())
  
  def set_state(new_state: TockyItemState):
    state.state = new_state
    if push:
      update_toc_queue(toc_queue_id, state.to_db_dict())

  set_state('Detecting')
  state.detector_result = run_with_result_stats(lambda: detector.detect(state.ocaid))

  if state.detector_result.error is not None:
    state.status = 'Errored'
    state.error = state.detector_result.error
    set_state('Errored')
    return state

  if not state.detector_result.result:
    state.status = 'No TOC detected'
  else:
    set_state('Extracting')
    state.extractor_result = run_with_result_stats(lambda: extractor.extract(state.ocaid, state.detector_result.result))

    state.toc_raw_ocr = extractor.toc_raw_ocr

    if state.extractor_result.error is not None:
      state.status = 'Errored'
      state.error = state.extractor_result.error
      set_state('Errored')
      return state
  

    state.structured_toc = state.extractor_result.result
    assert extractor.toc_response
    state.prompt_tokens = extractor.toc_response.prompt_tokens
    state.completion_tokens = extractor.toc_response.completion_tokens
    state.status = 'TOC Extracted'
    
    if state.structured_toc:
      total_pages = int(get_ia_metadata(state.ocaid)['metadata']['imagecount'])
      validation = validate_extracted_toc(state.structured_toc, total_pages)
      if validation != 'Valid':
        state.status = f'TOC Validation: {validation}'

  set_state('To Review')

  return state

class TockyOptionsError(ValueError):
    pass

def process_from_options(options: dict, push=False):
    if not options['input_book']['ia_id']:
        raise TockyOptionsError('IA ID is required')

    ia_id = options['input_book']['ia_id']

    # Set up detector
    DETECTOR_CLS = DETECTERS_BY_NAME.get(options['detector']['type'])
    if not DETECTOR_CLS:
        raise TockyOptionsError(f'Invalid detector type: {options["detector"]["type"]}')

    detector = DETECTOR_CLS()
    try:
        detector.P = dataclasses.replace(detector.P, **options['detector']['options'])
    except TypeError as e:
        # TODO: This will not error if things are set to the wrong type
      raise TockyOptionsError(f'Invalid detector options: {e}')

    # Run extractor
    EXTRACTOR_CLS = EXTRACTORS_BY_NAME.get(options['extractor']['type'])
    if not EXTRACTOR_CLS:
        raise TockyOptionsError(f'Invalid extractor type: {options["extractor"]["type"]}')

    extractor = EXTRACTOR_CLS()
    try:
        extractor.P = dataclasses.replace(extractor.P, **options['extractor']['options'])
    except TypeError as e:
        # TODO: This will not error if things are set to the wrong type
        raise TockyOptionsError(f'Invalid extractor options: {e}')
    # Share cache
    extractor.S = detector.S

    # Now let's run some stuff!
    detector.debug = False    
    return process_ia_book(ia_id, detector, extractor, push=push)


def push_to_toc_queue(record: dict) -> int:
  resp = requests.put(
      f'{get_env().get_app_prefix()}/push',
      headers={
          'X-API-KEY': get_env().TOCKY_SERVER_KEY,
          'Content-Type': 'application/json',
      },
      data=json.dumps(record)
  ).json()
  return resp['id']

def update_toc_queue(row_id: int, record: dict):
  return requests.post(
      f'{get_env().get_app_prefix()}/update/{row_id}',
      headers={
          'X-API-KEY': get_env().TOCKY_SERVER_KEY,
          'Content-Type': 'application/json',
      },
      data=json.dumps(record)
  ).json()

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
      push_to_toc_queue(result.to_db_dict())
      if result.error:
        print(traceback.print_exception(result.error))
      all_results.append(result)
  return all_results

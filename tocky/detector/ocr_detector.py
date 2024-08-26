from dataclasses import dataclass
import itertools
import re
from typing import Literal

from lxml import etree

from tocky.detector import AbstractDetector
from tocky.utils.ia import extract_leaf_num, get_djvu_pages, get_page_scan, ocaid_to_djvu_url
from tocky.ocr import ocr_djvu_page
from tocky.utils import avg_ocr_conf

TOC_PAGE_DETECTOR_VERSION = [
    ('v2.E.4', 'Check more pages for TOC if TOC has begun'),
    ('v2.E.3', 'Handle pages with all non-numeric pagenums'),
    ('v2.E.2', 'Add support for appendix page numbers like [A-C]123'),
    ('v2.E.1', 'Fix: Don\'t check every page after TOC found!'),
    ('v2.E.0', 'Add support for re-ocring when ending TOC range to avoid missing last page(s)'),
    ('v2.D.0', 'Add support for re-ocring previous page once first TOC page detected to avoid missing first page'),
]

POSSIBLE_PAGENUM_RE = re.compile(r'\b([ABC]?\d+|[xvil]+)$', re.IGNORECASE)
NEGATIVE_RE = re.compile(r'\d[.,-]\d+$')

def match_possible_pagenum(text: str) -> re.Match | None:
  """
  Matches things like:
  - 1
  - A1 (eg https://archive.org/details/calculusearlytra0000stew_08th/page/n13)
  - xii

  >>> bool(match_possible_pagenum('1'))
  True
  >>> bool(match_possible_pagenum('Appendix 1: Science A1'))
  True
  >>> bool(match_possible_pagenum('preface xii'))
  True
  >>> bool(match_possible_pagenum('1.32'))
  False
  >>> bool(match_possible_pagenum('1,32'))
  False
  >>> bool(match_possible_pagenum('1-32'))
  False
  """
  if (m := POSSIBLE_PAGENUM_RE.search(text)) and NEGATIVE_RE.search(text) is None:
    return m
  else:
    return None

def pagenum_word_to_int(n: str) -> int | None:
  """
  >>> pagenum_word_to_int('1')
  1
  >>> pagenum_word_to_int('A1')
  1
  >>> pagenum_word_to_int('xii')
  >>> pagenum_word_to_int('   432')
  432
  """
  n = n.strip()
  if n.isnumeric():
    return int(n)
  elif n[0].isalpha() and n[1:].isnumeric():
    return int(n[1:])
  else:
    return None

@dataclass
class OcrDetectorOptions:
  ocr_engine: Literal['easyocr', 'tesseract', 'azure'] = 'easyocr'
  allow_reocr: bool = True

class OcrDetector(AbstractDetector[OcrDetectorOptions]):
  name = 'ocr_detector'

  def __init__(self):
    super().__init__()
    self.P = OcrDetectorOptions()

  def predict_cost(self):
    return 0

  def detect(self, ocaid: str) -> list[int]:
    results = list(self.extract_toc_pages(ocaid))
    self.S.ocr_cache.update({
        extract_leaf_num(page_name): djvu_xml_str
        for (page_name, djvu_xml_str) in results
    })
    return [extract_leaf_num(page_name) for (page_name, _) in results]
  
  def extract_toc_pages(self, ocaid: str):
    return self.detect_table_of_contents_pages(ocaid_to_djvu_url(ocaid))

  def detect_table_of_contents_pages(self, djvu_url: str):
    has_begun = False
    for (page_name, elem_str, toc_analysis) in self.analyze_djvu_for_toc(djvu_url):
      if has_begun and not toc_analysis.is_toc:
        break
      if toc_analysis.is_toc:
        has_begun = True
        yield (page_name, elem_str)

  def analyze_djvu_for_toc(self, djvu_url: str):
    P = TOCDetectorHyperParams()
    has_begun = False
    reocrs_done = 0
    last_result: tuple[str, etree._Element, PageTocDetectionResult] = None
    for page_name, elem in get_djvu_pages(djvu_url, 1, end=None):
      toc_analysis = self.analyze_page_for_toc(elem, has_begun, allow_reocr=self.P.allow_reocr and (has_begun or reocrs_done < 10))
      if toc_analysis.reran_ocr:
        reocrs_done += 1
      # Let's check predecessor with redone ocr
      if self.P.allow_reocr and not has_begun and toc_analysis.is_toc and last_result and not last_result[2].reran_ocr:
        # Check if number is too high before redoing OCR
        recheck_previous = False
        for line in elem.findall(".//LINE"):
            words = line.findall(".//WORD")
            if words:
              last_word = words[-1]
              # Roman numerals are usually at the beginning of the book,
              # so need to check the previous page
              if bool(re.search(r'\b([xvil]+)$', last_word.text)):
                recheck_previous = False
                break

              # If it's just a normal numbers, if the number is too high,
              # then we should recheck the previous page
              if number_m := re.search(r'\b(\d+)$', last_word.text):
                n = int(number_m[1])
                recheck_previous = n > 25
                break
            
              # Other page numbers, like A1, B1, C1, etc are usually at
              # the end of the book in the appendix, so we should recheck
              # the previous page
              if match_possible_pagenum(last_word.text):
                recheck_previous = True
                break

        if recheck_previous:
          new_toc_analysis = self.analyze_page_for_toc(last_result[1], False, redo_ocr=True)
          reocrs_done += 1
          if new_toc_analysis.is_toc:
            last_result = (last_result[0], last_result[1], new_toc_analysis)

      if self.P.allow_reocr and has_begun and not toc_analysis.is_toc and not toc_analysis.reran_ocr:
        # Let's try again with rerun ocr
        reocrs_done += 1
        toc_analysis = self.analyze_page_for_toc(elem, has_begun, redo_ocr=True)

      # Yield the thing we know won't change anymore
      if last_result:
        yield (last_result[0], etree.tostring(last_result[1], encoding='unicode'), last_result[2])

      has_begun = toc_analysis.is_toc
      last_result = (page_name, elem, toc_analysis)

      leaf_num = extract_leaf_num(page_name)
      if has_begun and leaf_num > P.max_leaf_to_check_while_in_toc:
        break
      if not has_begun and leaf_num > P.max_leaf_to_check:
        break

    if last_result:
      yield (last_result[0], etree.tostring(last_result[1], encoding='unicode'), last_result[2])

  def analyze_page_for_toc(
    self,
    elem: etree._Element,
    has_begun = False,
    allow_reocr=True,
    redo_ocr=False,
  ) -> 'PageTocDetectionResult':
    hiddentext = elem.find(".//HIDDENTEXT")
    if hiddentext is None:
      return PageTocDetectionResult(False, 'Missing hiddentext')

    P = TOCDetectorHyperParams()
    result = PageTocDetectionResult()

    page_file: str = elem.xpath('./@usemap')[0]
    ocaid = page_file.rsplit('_', 1)[0]
    leaf_num = extract_leaf_num(page_file)
    # print('analyze_page_for_toc', page_file, f'{allow_reocr=}')

    def do_redo_ocr(min_conf: float):
      if elem.xpath('.//HIDDENTEXT/@x-re-ocrd') == ['true']:
        return
      new_ocr = ocr_djvu_page(get_page_scan(ocaid, leaf_num), engine=self.P.ocr_engine)
      result.reran_ocr = True
      new_ocr_el = etree.fromstring(new_ocr).find('.//HIDDENTEXT')
      # Re-OCR will always output confidences, so assume 100 (likely empty page)
      new_conf = avg_ocr_conf(new_ocr_el) or 100
      # print(f'{page_file} mean_conf {(mean_conf or 0):.2f} -> {new_conf:.2f}')
      if new_conf > min_conf:
        result.used_new_ocr = True
        elem.replace(elem.find('.//HIDDENTEXT'), new_ocr_el)
        return self.analyze_page_for_toc(elem, has_begun, allow_reocr=False, redo_ocr=False)

    mean_conf = avg_ocr_conf(elem)

    if redo_ocr:
      if new_result := do_redo_ocr(min_conf=(mean_conf or 0) - 15):
        return new_result

    if mean_conf is not None and mean_conf < P.min_mean_word_confidence:
      if allow_reocr:
        if new_result := do_redo_ocr(min_conf=mean_conf):
          return new_result
      return PageTocDetectionResult(False, f'Mean page confidence too low ({mean_conf:.2f} < {P.min_mean_word_confidence})')

    # If there are more than 40 words and the average right coord of each word is
    # less than 2/3 width of page, then potentially should re-ocr cause mis-OCR'd
    # pages
    if allow_reocr:
      word_rights = [
          int(coord.split(',')[2])
          for coord in hiddentext.xpath('.//WORD/@coords')
      ]
      if len(word_rights) > 70:
        width = int(elem.xpath('./@width')[0])
        words_near_right = len([r for r in word_rights if r > width * .8 ])

        words_near_right_text = [
            word.text
            for word in hiddentext.xpath('.//WORD')
            if int(word.xpath('./@coords')[0].split(',')[2]) > width * .8
        ]
        numeric_words_near_right = len([
            word
            for word in words_near_right_text
            if match_possible_pagenum(word)
        ])
        # print(f'{words_near_right=}, {numeric_words_near_right=} of {len(word_rights)=}')
        if (words_near_right - numeric_words_near_right) < 3:
          if new_result := do_redo_ocr(min_conf=(mean_conf or 0) - 15):
            return new_result


    numbers_at_end_of_lines = []
    for line in hiddentext.findall(".//LINE"):
        words = line.findall(".//WORD")
        if words:
          last_word = words[-1]
          if m := match_possible_pagenum(last_word.text):
              confidence = last_word.xpath('./@x-confidence')
              bad_ocr = confidence and float(confidence[0]) < P.min_word_confidence
              if len(m.group()) == 1 and bad_ocr:
                # Exclude, likely noise
                pass
              else:
                numbers_at_end_of_lines.append(m.group())

    from collections import Counter
    max_repeated = max(Counter(numbers_at_end_of_lines).values(), default=0)
    lines_w_uniq_nums = len(set(numbers_at_end_of_lines))

    if max_repeated > P.max_repeated_nums:
      return PageTocDetectionResult(False, 'Too many repeated numbers')

    if lines_w_uniq_nums < P.min_lines_with_nums:
      return PageTocDetectionResult(False, f'Not enough lines with nums ({lines_w_uniq_nums} < {P.min_lines_with_nums})')

    if lines_w_uniq_nums > P.max_lines_with_nums:
      return PageTocDetectionResult(False, 'Too many lines with nums')

    nums = [
        num
        for n in numbers_at_end_of_lines
        if (num := pagenum_word_to_int(n)) is not None
    ]

    if len(nums) > 4:
      increasing_count = 0
      non_increasing_count = 0
      for (prev, cur) in itertools.pairwise([0] + nums):
        if prev <= cur:
          increasing_count += 1
        else:
          non_increasing_count += 1

      increasing_percent = increasing_count / (increasing_count + non_increasing_count)
      if increasing_percent < P.min_increasing_percent:
        return PageTocDetectionResult(False, f'Not enough of the nums are increasing {increasing_percent:.2f} < {P.min_increasing_percent}')

    if has_begun:
      first_line = ' '.join(word.text for word in hiddentext.find(".//LINE").findall(".//WORD"))
      if 'illustration' in first_line.lower() or 'index' in first_line.lower() or 'figure' in first_line.lower() or 'tables' in first_line.lower():
        return PageTocDetectionResult(False, 'Contains illustration/index')
    else:
      small_nums_count = len([n for n in numbers_at_end_of_lines if len(n) < 4])
      if small_nums_count < P.min_small_nums_count_for_first:
        return PageTocDetectionResult(False, 'Not enough small numbers for first TOC page')

      # Check average word length probably bad OCR on empty page
      word_lens = [
          len(word.text.strip())
          for word in elem.findall('.//WORD')
          # Skip non-word-y things
          if not match_possible_pagenum(word.text) and not re.search(r'^[\.^;:{}]+$', word.text.strip())
      ]
      avg_word_len = sum(word_lens) / len(word_lens)
      if avg_word_len < P.min_avg_word_len:
        return PageTocDetectionResult(False, f'Average word length too low {avg_word_len:.2f} < {P.min_avg_word_len}')

    if allow_reocr:
      if new_result := do_redo_ocr(min_conf=(mean_conf or 0) - 15):
        return new_result

    return PageTocDetectionResult(True)


@dataclass
class TOCDetectorHyperParams:
  min_lines_with_nums: int = 5
  max_lines_with_nums: int = 50
  max_repeated_nums: int = 4
  min_word_confidence: float = 40
  min_mean_word_confidence: float = 30
  min_small_nums_count_for_first: int = 4
  min_avg_word_len: float = 3.8
  min_increasing_percent: float = 0.75
  max_leaf_to_check: int = 28
  max_leaf_to_check_while_in_toc: int = 30


@dataclass
class PageTocDetectionResult:
  is_toc: bool = False
  failure: str | None = None
  reran_ocr: bool = False
  used_new_ocr: bool = False

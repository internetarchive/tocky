from dataclasses import dataclass, field
from typing import Literal, Any

from tocky.detector.ocr_detector import OcrDetector, extract_page_index, ocaid_to_djvu_url

@dataclass
class TestCase:
  ocaid: str
  toc_pages: list[str]
  custom_labels: list[str] = field(default_factory=list)

  @property
  def labels(self):
    labels = list(self.custom_labels)
    if len(self.toc_pages) == 0:
      labels.append('No TOC')
    elif len(self.toc_pages) == 1:
      labels.append('Single Page TOC')
    else:
      labels.append('Multi Page TOC')

    return labels

test_set = [
    TestCase('countofmontecris01duma', ['0013'], ['Has List of Illustrations']),
    TestCase('travelsinmexicod01gill', []),
    TestCase('davidpoindexters00hawt', ['0007']),
    TestCase('harvardclassicss18elio', ['0005', '0006']),
    TestCase('prideprejudice0000unse_r8e0', [], ['Has List of Illustrations']),
    TestCase('englishstruwwelp00hoffrich', []),
    TestCase('janeeyreautobiog01bron', []),
    TestCase('cu31924013243963', ['0012', '0013'], ['Has List of Illustrations']),
    TestCase('adventuresofsher00doylrich', ['0011'], ['Has List of Illustrations', 'Contents page has bad OCR']),
    TestCase('cihm_93635', [], ['Microfilm']),
    TestCase('murderofrogerack0000agat_g7y3', ['0011'], ['Printing history on copyright page']),
    TestCase('alicesadventures0000lewi_h0b9', ['0015']),
    TestCase('dracu00stok', ['0013', '0014', '0015'], ['page numbers are not separate words']),
    TestCase('odysseybookiv00home', [], ['bad OCR on blank page']),
    TestCase('the-great-gatsby', []),
    TestCase('olivertwist0000char_v6j2', ['0015', '0016', '0017']),
    TestCase('littleprincessbe00burn', ['0017'], ['Has List of Illustrations']),
    TestCase('alicesadventures0000unse_r2e4', ['0009', '0010'], ['Contents page has bad OCR']),
    TestCase('dianearbuss1960s0000gros', ['0009']),
    TestCase('meditationsofmar00marc', ['0009']),
    TestCase('kingjamesfirstdm00jame', []),
    TestCase('kamasutraofvatsy00vatsuoft', ['0011']),
    TestCase('gameoflifehowtop00shin', ['0005']),
    TestCase('alanturingenigma0000hodg', ['0011']),
    # Super slow
    # TestCase('dictionaryofprin00drozrich', [], ['bad OCR on blank page']),
    TestCase('b24884431', [], ['Has a table in front matter']),
    TestCase('artofpersuasionw0000burg', ['0011', '0012'], ['Contents page has bad OCR']),
    TestCase('atomichabitseasy0000clea', ['0009', '0010', '0011'], ['bad OCR on blank page']),
    TestCase('dressmakingselft00care', ['0009', '0010', '0011', '0012', '0013'], ['Sparse TOC pages']),
    TestCase('whoswhoincanada0072unse', [], ['Index at front']),
    TestCase('20yearsevergood0000unse', ['0013'], ['Weird TOC format']),
    TestCase('isbn_9780039105167', ['0007', '0008'], ['Contents page has bad OCR']),
    TestCase('b2892907x', [], ['Has a table in front matter']),
    TestCase('civilwarnarrativ0000foot_w4t8', ['0011'], ['bad OCR on blank page']),
    TestCase('pilgrimmemorials00russ_0', [], ['Index at front']),
    TestCase('agriculturalpoli0000elli', ['0009', '0010', '0011', '0012'], ['Dense TOC']),
    TestCase('leipzeigtrialsac00mull', ['0025'], ['TOC after page 20']),
    TestCase('coloradosrodeoro0000ordw', ['0009'], ['Contents page has bad OCR']),
    TestCase('dirtylaundry0000cull', ['0009'], ['Contents page has bad OCR']),
    TestCase('employmentlaw06edcarr', ['0005', '0006', '0007']),
    TestCase('solarcellstheira0000unse', [f'{d:04}' for d in range(9, 20)], ['Contents page has bad OCR']),
    TestCase('warsoffrenchdeco0000clay', ['0007', '0008', '0009']),
    TestCase('piepiepieeasyhom0000carr', ['0008', '0009'], ['Page numbers on left of TOC entries']),
    TestCase('essentialspanish00nova', ['0009', '0010', '0011', '0012', '0013', '0014', '0015']),
    TestCase('davidsonsessenti0000unse_k5e3', ['0009'], ['Contents page has bad OCR']),
    TestCase('whyscientistsdis0000unse', ['0011'], ['Contents page has bad OCR']),
    TestCase('plowsplantingimp0000halb', ['0007']),
    TestCase('phonicsphonemica0000cala', ['0004']),
    TestCase('writingtohealgui0000penn', ['0007', '0008']),
    TestCase('prayersfromseaso0000deck', ['0007', '0008'], ['Contents page OCR missing numbers']),
    TestCase('artbasedgames0000pave', ['0007', '0008']),
    TestCase('transitionfromsc0000unse', ['0007', '0008', '0009']),
    TestCase('workbookofphotog0000hedg', ['0006', '0007'], ['Many entires']),
    TestCase('subtleartofnotgi0000mans_n2n5', ['0005', '0006', '0007']),
    TestCase('digitalphotograp00shep', [f'{d:04}' for d in range(8, 13)])
    #TestCase('', []),
]

@dataclass
class TestResult:
  test: TestCase
  status: Literal['PASS',  'FAIL', 'ERRO']
  actual: Any
  reasons: Any

def run_test(test: TestCase) -> TestResult:
  expected_pages = [int(p) for p in test.toc_pages]
  pages_to_see = set(expected_pages)
  test_passes = True
  reasons = {}
  has_begun = False
  has_ended = False
  toc_pagenums = []
  for (pagenum, xml_str, toc_analysis) in OcrDetector().analyze_djvu_for_toc(ocaid_to_djvu_url(test.ocaid)):
    pagen = extract_page_index(pagenum)

    has_begun = has_begun or toc_analysis.is_toc
    is_expected = pagen in expected_pages

    if toc_analysis.is_toc:
      toc_pagenums.append(pagen)
    if has_begun and not toc_analysis.is_toc:
      has_ended = True

    if toc_analysis.is_toc == is_expected == True:
      # We good!
      pass
    elif not toc_analysis.is_toc and is_expected:
      test_passes = False
      reasons[pagen] = toc_analysis.failure
    elif toc_analysis.is_toc and not is_expected:
      test_passes = False
      reasons[pagen] = 'Wrong TOC page'

    if is_expected:
      pages_to_see.remove(pagen)
    if has_ended and not pages_to_see:
      break

  result = [f'{n:04}' for n in toc_pagenums]
  return TestResult(test, 'PASS' if result == test.toc_pages else 'FAIL', result, reasons)

def run_all_tests(test_set: list[TestCase]):
  import concurrent.futures

  icon_mapping = {
    'PASS': '✔️',
    'FAIL': '❌',
    'ERRO': '💥',
  }

  def process_test(test):
    result = run_test(test)
    icon = icon_mapping[result.status]
    print(f'{icon} {result.test.ocaid}')
    if result.status != 'PASS':
        print('Expected:', result.test.toc_pages)
        print('Actual:', result.actual)
        print('Links:', [f"https://archive.org/details/{result.test.ocaid}/page/leaf{n}/mode/1up" for n in result.actual])
        print('Labels:', result.test.labels)
        print('Reasons:', result.reasons)

    return result

  with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
      return list(executor.map(process_test, test_set))

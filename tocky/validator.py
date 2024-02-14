from dataclasses import dataclass

@dataclass
class TocEntry:
    level: int
    label: str
    title: str
    pagenum: str


class OlTocParseError(Exception):
  pass


def parse_ol_toc(toc_string: str) -> List[TocEntry]:
    toc_entries = []
    lines = toc_string.strip().split('\n')
    pattern = r'''
        ^\s*
        (?P<stars>\*+)      # Capture stars
        \s*
        \|
        \s*
        (?P<label>[^|]+)     # Capture label
        \s*
        \|
        \s*
        (?P<pagenum>\S.*)     # Capture page number
        $                    # End of line
    '''

    for line in lines:
        # Chat GPT started outputting these lately
        if line.strip() == '```':
          continue
        parts = line.strip().split('|')
        if len(parts) != 3:
          raise OlTocParseError()
        label, title, pagenum = parts
        if not label.startswith('*'):
          raise OlTocParseError()
        toc_entries.append(
            TocEntry(
              level=len(re.search(r'\*+', label)[0]),
              label=label.lstrip('* ').rstrip(),
              title=title.strip(),
              pagenum = pagenum.strip(),
          )
        )

    return toc_entries


def validate_extracted_toc(toc_str: str, num_pages: int):
  try:
    parsed_toc = parse_ol_toc(toc_str)
  except OlTocParseError:
    return 'Unparseable TOC'

  for entry in parsed_toc:
    if len(entry.label) > 160 or len(entry.title) > 160:
      return 'Label/Title Too Long'

  nums = [
    int(entry.pagenum)
    for entry in parsed_toc
    if entry.pagenum.isnumeric()
  ]
  roman_numerals = [
    entry.pagenum
    for entry in parsed_toc
    if re.search(r'^[xvi]+$', entry.pagenum, flags=re.IGNORECASE)
  ]

  if not (nums + roman_numerals):
    return 'No Numbers'

  if len(nums + roman_numerals) < 2:
    return 'Not Enough Numbers'

  if len(nums + roman_numerals) < (len(parsed_toc) * 0.7):
    return 'Too Few Lines With Numbers'

  if not roman_numerals and (nums[0] > 40 and nums[1] > 40):
    return 'Starts Too High'

  if num_pages > 150 and nums[-1] < (num_pages - 150) and nums[-2] < (num_pages - 150):
    return 'End Too Low'

  return 'Valid'
import math
from typing import Literal, cast
from lxml import etree
from rtree import index

from tocky.utils.ia import get_ia_metadata

def ocr_printer_linear(djvu_page: str | etree._Element) -> str:
    if isinstance(djvu_page, str):
       root = etree.fromstring(djvu_page)
    else:
        root = djvu_page

    result = ""

    ref_word = next(
        word
        for word in root.findall('.//WORD')
        if len(word.text) > 8
    )
    ref_word_coords = ref_word.xpath("./@coords")[0].split(',')
    ref_word_width = int(ref_word_coords[2]) - int(ref_word_coords[0])
    char_width = ref_word_width / len(ref_word.text)

    for pagecol in root.findall('.//PAGECOLUMN'):
        for par in pagecol.findall('.//PARAGRAPH'):
            for line in par.findall('.//LINE'):
                words = line.findall('.//WORD')
                if words:
                    coords = line.xpath('.//WORD/@coords')[0].split(',')

                    line_indent = math.floor(int(coords[0]) / char_width)
                    line_text = ' '.join(word.text.strip() for word in words)
                    indented_line = ' ' * line_indent + line_text
                    result += indented_line + '\n'

    return result

def ocr_printer_canvas(djvu_page: str | etree._Element) -> str:
    if isinstance(djvu_page, str):
       root = etree.fromstring(djvu_page)
    else:
        root = djvu_page
    canvas = ""

    # Convert inches to pixels
    dpi = int((root.xpath(".//PARAM[@name='DPI']/@value") or [int(get_ia_metadata(ocaid)['metadata']['ppi'])])[0])
    line_rounding_size = round(0.0333 * dpi)
    img_width = int(root.xpath('./@width')[0])
    img_height = int(root.xpath('./@height')[0])

    canvas_width = 120  # dpi // 4
    conv_factor = canvas_width / img_width
    canvas_height = math.ceil(img_height * conv_factor)
    canvas = ((" " * canvas_width + '\n') * canvas_height)[:-1]

    def build_index(conv_factor: float, line_rounding_size: int) -> index.Index:
        regions = index.Index()
        rect_index = 0
        for pagecol in root.findall('.//PAGECOLUMN'):
            for par in pagecol.findall('.//PARAGRAPH'):
                for line in par.findall('.//LINE'):
                    # log('LINE')
                    line_row = None
                    for word in line.findall('.//WORD'):
                        coords = word.xpath('./@coords')[0].split(',')
                        left = int(coords[0])
                        bottom = int(coords[1])
                        right = int(coords[2])
                        top = int(coords[3])

                        baseline = round((top + (bottom - top) / 3) / line_rounding_size) * line_rounding_size
                        line_row = math.floor(baseline * conv_factor) if line_row is None else line_row
                        col = math.floor(left * conv_factor)

                        while list(regions.intersection(rect := (col, line_row, col + len(word.text), line_row + 1))):
                            col += 1

                        regions.insert(rect_index, rect, obj=word.text)
                        rect_index += 1

        return regions


    def build_canvas(regions: index.Index, canvas_width: int, canvas_height: int) -> str:
        canvas = ((" " * canvas_width + '\n') * canvas_height)[:-1]
        for item in regions.intersection(regions.bounds, objects=True):
            word = cast(str, item.object)
            line_row = int(item.bbox[1])
            col = int(item.bbox[0])

            start_idx = (canvas_width + 1) * line_row + col
            end_idx = start_idx + len(word)
            # shift = 0
            # max_shift = 5
            # log(f'{line_row}:{col}\t{coords}\t{word.text}')
            # while not canvas[max(0, start_idx - 1):(end_idx + 1)].isspace():
            #   start_idx += 1
            #   end_idx += 1
            #   shift += 1
            #   if shift >= max_shift:
            #     break
            canvas = canvas[0:start_idx] + word + canvas[end_idx:]
        return canvas
       

    def crop_text_canvas(canvas: str, used_regions: index.Index) -> str:
      lines = canvas.split('\n')
      left, bottom, right, top = list(map(int, used_regions.bounds))

      return '\n'.join((
          line[left:right] if not line.isspace() else ''
          for line in lines[bottom:top]
      ))

    def collapse_newlines(s: str):
        import re
        min_newline_chain = min(map(len, re.findall(r'\n+', s.strip(), re.MULTILINE)), default=1)

        return re.sub(r'\n' * (min_newline_chain -1) + '(\n*)', r'\1', s, flags=re.MULTILINE)
        # return re.sub(r'\n+', '\n', s, flags=re.MULTILINE)

    def collapse_spaces(s: str):
        import re
        min_newline_chain = min(map(len, re.findall(r' +', s.strip(), re.MULTILINE)), default=1)

        return re.sub(r' ' * (min_newline_chain -1) + '( *)', r'\1', s, flags=re.MULTILINE)
        # return re.sub(r'(\S) +', r'\1 ', s)

    def crunch_solos(regions: index.Index):
        def shrink_rect(rect: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
            return (rect[0] + 0.1, rect[1] + 0.1, rect[2] - 0.1, rect[3] - 0.1)

        prev_rects_on_line = []
        for row_i in range(int(regions.bounds[1]), int(regions.bounds[3] + 1)):
            row_rect = (0, row_i + 0.1, canvas_width, row_i + 0.9)
            rects_on_line = list(n for n in regions.intersection(row_rect, objects=True))

            # Can I move up?
            if len(rects_on_line) == 1 and prev_rects_on_line:
                item = rects_on_line[0]
                rect = item.bbox
                new_rect = (rect[0], rect[1] - 1, rect[2], rect[3] - 1)
                
                if not any(regions.intersection(shrink_rect(new_rect))):
                    regions.delete(item.id, rect)
                    regions.insert(item.id, new_rect, obj=item.object)

                    rects_on_line = list(n for n in regions.intersection(row_rect, objects=True))
            # Can I pull predecessor?
            elif len(prev_rects_on_line) == 1 and rects_on_line:
                item = prev_rects_on_line[0]
                rect = item.bbox
                new_rect = (rect[0], rect[1] + 1, rect[2], rect[3] + 1)
                if not any(regions.intersection(shrink_rect(new_rect))):
                    regions.delete(item.id, rect)
                    regions.insert(item.id, new_rect, obj=item.object)

                    rects_on_line = list(n for n in regions.intersection(row_rect, objects=True))

            prev_rects_on_line = rects_on_line


    regions = build_index(conv_factor, line_rounding_size)
    crunch_solos(regions)
    canvas = build_canvas(regions, canvas_width, canvas_height)

    return collapse_newlines(crop_text_canvas(canvas, regions))

def print_ocr(djvu_xml: str | etree._Element, printer: Literal['canvas', 'linear']='canvas') -> str:
  if printer == 'canvas':
    return ocr_printer_canvas(djvu_xml)
  elif printer == 'linear':
    return ocr_printer_linear(djvu_xml)
  else:
    raise ValueError(f'Invalid printer type: {printer}')
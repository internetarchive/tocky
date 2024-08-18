import requests
from tocky.utils import PageScan
from lxml import etree
import os

def ocr_djvu_page_azure(page_scan: PageScan) -> str:
    subscription_key = os.getenv("AZURE_SUBSCRIPTION_KEY")
    endpoint = os.getenv("AZURE_ENDPOINT")
    ocr_url = endpoint + "vision/v3.2/ocr"

    headers = {
        'Ocp-Apim-Subscription-Key': subscription_key,
        'Content-Type': 'application/octet-stream'
    }

    response = requests.post(ocr_url, headers=headers, data=page_scan.image.tobytes())
    response.raise_for_status()
    analysis = response.json()

    lines = []
    for region in analysis['regions']:
        for line in region['lines']:
            line_el = etree.Element('LINE')
            for word in line['words']:
                word_el = etree.Element('WORD')
                word_el.set('coords', f"{word['boundingBox']}")
                word_el.set('x-confidence', '100')  # Azure OCR does not provide confidence
                word_el.text = word['text']
                line_el.append(word_el)
            lines.append(etree.tostring(line_el, encoding='unicode'))

    return (
        f'<OBJECT type="image/x.djvu" width="{page_scan.width}" height="{page_scan.height}">\n'
        f'<PARAM name="DPI" value="{page_scan.dpi}"/>\n'
        '<HIDDENTEXT x-re-ocrd="true">'
        '<PAGECOLUMN>'
        '<REGION>'
        '<PARAGRAPH>\n' + '\n'.join(lines) + '\n</PARAGRAPH>'
        '</REGION>'
        '</PAGECOLUMN>'
        '</HIDDENTEXT>'
        '</OBJECT>'
    )

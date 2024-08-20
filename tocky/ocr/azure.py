import io
from typing import TypedDict, cast
import requests
from tocky.utils import PageScan
from lxml import etree
import os
from PIL import Image

class AzureOcrResponse(TypedDict):
    modelVersion: str
    metadata: 'AzureOcrMetadata'
    readResult: 'AzureOcrReadResult'

class AzureOcrReadResult(TypedDict):
    blocks: list['AzureOcrBlock']

class AzureOcrBlock(TypedDict):
    lines: list['AzureOcrLine']

class AzureOcrMetadata(TypedDict):
    width: int
    height: int

# EG {
#     "text": "9:35 AM",
#     "boundingPolygon": [{"x":131,"y":130},{"x":214,"y":130},{"x":214,"y":148},{"x":131,"y":148}],
#     "words": [{"text":"9:35","boundingPolygon":[{"x":132,"y":130},{"x":172,"y":131},{"x":171,"y":149},{"x":131,"y":148}],"confidence":0.977},{"text":"AM","boundingPolygon":[{"x":180,"y":131},{"x":203,"y":131},{"x":202,"y":149},{"x":180,"y":149}],"confidence":0.998}]
# },
class AzureOcrLine(TypedDict):
    text: str
    boundingPolygon: list['AzureOcrPoint']
    """
    Order of points is top-left, top-right, bottom-right, bottom-left
    """

    words: list['AzureOcrWord']

class AzureOcrPoint(TypedDict):
    x: int
    y: int

class AzureOcrWord(TypedDict):
    text: str
    boundingPolygon: list[AzureOcrPoint]
    confidence: float

def image_to_bytes(image: Image.Image) -> bytes:
    with io.BytesIO() as output:
        image.save(output, format='JPEG')
        return output.getvalue()

def fetch_ocr_azure(image: Image.Image) -> AzureOcrResponse:
    subscription_key = os.getenv("AZURE_SUBSCRIPTION_KEY")
    endpoint = os.getenv("AZURE_ENDPOINT")

    assert subscription_key, "Set the AZURE_SUBSCRIPTION_KEY environment variable."
    assert endpoint, "Set the AZURE_ENDPOINT environment variable."

    endpoint = endpoint.rstrip('/')

    response = requests.post(
        f'{endpoint}/computervision/imageanalysis:analyze',
        params={
            'features': 'read',
            'model-version': 'latest',
            'language': 'en',
            'api-version': '2024-02-01',
        },
        headers={
            'Ocp-Apim-Subscription-Key': subscription_key,
            'Content-Type': 'application/octet-stream'
        },
        data=image_to_bytes(image)
    )
    # response.raise_for_status()
    return cast(AzureOcrResponse, response.json())

def azure_read_result_to_djvu_xml(read_result: AzureOcrReadResult) -> str:
    paragraphs = []
    for block in read_result['blocks']:
        paragraph = etree.Element('PARAGRAPH')

        for line in block['lines']:
            line_el = etree.Element('LINE')
            for word in line['words']:
                word_el = etree.Element('WORD')
                rect = word['boundingPolygon']
                # coords is LBRT
                word_el.set('coords', ','.join(
                    str(x) for x in (
                        min(rect[0]["x"], rect[3]["x"]),
                        max(rect[2]["y"], rect[3]["y"]),
                        max(rect[1]["x"], rect[2]["x"]),
                        min(rect[0]["y"], rect[1]["y"]),
                    )
                ))
                word_el.set('x-confidence', str(100 * word['confidence']))
                word_el.text = word['text']
                line_el.append(word_el)
            paragraph.append(line_el)

        paragraphs.append(etree.tostring(paragraph, encoding='unicode'))
    return '\n'.join(paragraphs)

def ocr_djvu_page_azure(page_scan: PageScan) -> str:
    azure_response = fetch_ocr_azure(page_scan.image)

    return (
        f'<OBJECT type="image/x.djvu" width="{page_scan.width}" height="{page_scan.height}">\n'
        f'<PARAM name="DPI" value="{page_scan.dpi}"/>\n'
        '<HIDDENTEXT x-re-ocrd="true">'
        '<PAGECOLUMN>'
        '<REGION>'
        + azure_read_result_to_djvu_xml(azure_response['readResult']) +
        '</REGION>'
        '</PAGECOLUMN>'
        '</HIDDENTEXT>'
        '</OBJECT>'
    )

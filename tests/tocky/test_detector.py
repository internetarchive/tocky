from lxml import etree
from unittest.mock import patch

from tocky.detector.ocr_detector import OcrDetector

class Test_analyze_page_for_toc:
    def test_no_hiddentext(self):
        xml_str = build_test_page_object_str(hiddentext=False)
        elem = etree.fromstring(xml_str)
        result = OcrDetector().analyze_page_for_toc(elem, allow_reocr=False)
        assert result.is_toc == False

    def test_redo_ocr(self):
        xml_str = build_test_page_object_str()

        elem = etree.fromstring(xml_str)
        with patch('tocky.detector.ocr_detector.ocr_djvu_page') as mock_ocr_djvu_page:
            mock_ocr_djvu_page.return_value = build_test_page_object_str(re_ocrd=True)

            OcrDetector().analyze_page_for_toc(elem, redo_ocr=True)
            assert mock_ocr_djvu_page.call_count == 1

    def test_duplicate_redo_ocr(self):
        xml_str = build_test_page_object_str(re_ocrd=True)

        elem = etree.fromstring(xml_str)
        with patch('tocky.detector.ocr_detector.ocr_djvu_page') as mock_ocr_djvu_page:
            mock_ocr_djvu_page.return_value = build_test_page_object_str(re_ocrd=True)

            OcrDetector().analyze_page_for_toc(elem, redo_ocr=True)
            assert mock_ocr_djvu_page.call_count == 0

def build_test_page_object_str(hiddentext=True, re_ocrd=False):
    hiddentext_str = ""
    if hiddentext:
        hiddentext_str = f"""
            <HIDDENTEXT{' x-re-ocrd="true"' if re_ocrd else ''}>
                <PAGECOLUMN>
                    <REGION>
                        <PARAGRAPH>
                            <LINE>
                                <WORD coords="1052,148,1264,120" x-confidence="22">CHILDREN'S </WORD>
                                <WORD coords="1264,149,1356,125" x-confidence="29">BOOK</WORD>
                            </LINE>
                            <LINE>
                                <WORD coords="1103,197,1303,172" x-confidence="20">COLLECTION</WORD>
                            </LINE>
                        </PARAGRAPH>
                    </REGION>
                </PAGECOLUMN>
            </HIDDENTEXT>
        """

    return f"""
    <OBJECT data="file://localhost/var/tmp/autoclean/derive/goodytwoshoes00newyiala/goodytwoshoes00newyiala.djvu" type="image/x.djvu" usemap="goodytwoshoes00newyiala_0001.djvu" width="2454" height="3192">
        <PARAM name="PAGE" value="goodytwoshoes00newyiala_0001.djvu"/>
        <PARAM name="DPI" value="500"/>
        {hiddentext_str}
    </OBJECT>
    """
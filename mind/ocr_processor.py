import pytesseract
from pdf2image import convert_from_path
from PIL import Image
import os
import logging

class OCRProcessor:
    def __init__(self, dpi=150):
        self.dpi = dpi

    def ocr_image(self, image_path: str) -> str:
        try:
            img = Image.open(image_path)
            text = pytesseract.image_to_string(img)
            return text
        except Exception as e:
            logging.error(f"OCR on image failed: {e}")
            return ""

    def ocr_pdf(self, pdf_path: str) -> str:
        if not os.path.isfile(pdf_path):
            logging.error(f"OCR PDF failed, file not found: {pdf_path}")
            return ""
        try:
            pages = convert_from_path(pdf_path, dpi=self.dpi)
            texts = []
            for page in pages:
                text = pytesseract.image_to_string(page)
                texts.append(text)
            return "\n".join(texts)
        except Exception as e:
            logging.error(f"OCR on PDF failed: {e}")
            return ""
def pdf_to_text_pages(pdf_path: str, dpi: int = 150) -> str:
    """
    Wrapper around OCRProcessor.ocr_pdf so existing imports still work.
    """
    processor = OCRProcessor(dpi=dpi)
    return processor.ocr_pdf(pdf_path)

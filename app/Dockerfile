FROM python:3.10

# Choose the OCR engines to install. Note installing these increases the image size
# drastically. The available options are "tesseract" and "easyocr", or both! E.g.
# ARG OCR_ENGINES="tesseract easyocr"
ARG OCR_ENGINES=""

# Add the Tesseract OCR repository and install Tesseract OCR
RUN apt-get update \
    # only install tesseract if it is in the list of OCR engines
    && if echo $OCR_ENGINES | grep -q tesseract; then \
        apt-get install -y tesseract-ocr tesseract-ocr-eng libopencv-dev; \
    fi \
    && apt-get clean

RUN pip install poetry==1.7.1

ENV FLASK_APP=app.py \
    FLASK_RUN_HOST=0.0.0.0 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /tocky

COPY pyproject.toml poetry.lock ./
RUN poetry install --extras "app $OCR_ENGINES" --compile
COPY ./ /tocky

ENV PYTHONPATH=/tocky
WORKDIR /tocky/app

EXPOSE 5000

CMD ["poetry", "run", "uvicorn", "app.app:app", "--reload", "--port", "5000"]

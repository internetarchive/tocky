FROM python:3.10

# Add the Tesseract OCR repository and install Tesseract OCR
RUN apt-get update \
    && apt-get install -y tesseract-ocr tesseract-ocr-eng libopencv-dev \
    && apt-get clean

RUN pip install poetry

ENV FLASK_APP=app.py \
    FLASK_RUN_HOST=0.0.0.0 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /tocky

COPY pyproject.toml poetry.lock ./
RUN poetry install --with "app" --compile
COPY ./ /tocky

ENV PYTHONPATH=/tocky
WORKDIR /tocky/app

EXPOSE 5000

CMD ["flask", "run"]

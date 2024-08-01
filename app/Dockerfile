FROM python:3.11

# Install dependencies for adding repository
RUN apt-get update && apt-get install -y software-properties-common gnupg curl

# Add the Tesseract OCR repository and install Tesseract OCR
RUN curl -sSL https://notesalexp.org/tesseract-ocr/tesseract-ocr.list -o /etc/apt/sources.list.d/tesseract-ocr.list \
    && curl -sSL https://notesalexp.org/tesseract-ocr/notesalexp_signing.key | apt-key add - \
    && apt-get update \
    && apt-get install -y tesseract-ocr tesseract-ocr-eng \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Verify Tesseract version
RUN tesseract --version

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

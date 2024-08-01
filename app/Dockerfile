FROM python:3.11

# Install software-properties-common to add add-apt-repository command
RUN apt-get update && apt-get install -y software-properties-common

# Setup tesseract
RUN add-apt-repository -y ppa:alex-p/tesseract-ocr5 \
    && apt-get update \
    && apt-get install -y tesseract-ocr tesseract-ocr-eng \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

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

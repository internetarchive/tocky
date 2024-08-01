FROM python:3.11

RUN pip install poetry

ENV FLASK_APP=app.py \
    FLASK_RUN_HOST=0.0.0.0 \
    POETRY_VIRTUALENVS_CREATE=false

# Setup tesseract (tmp: move to a separate image)
RUN add-apt-repository -y ppa:alex-p/tesseract-ocr5 \
    && apt-get update \
    && apt-get install -y tesseract-ocr tesseract-ocr-eng

WORKDIR /tocky

COPY pyproject.toml poetry.lock ./
RUN poetry install --with "app" --compile
COPY ./ /tocky

ENV PYTHONPATH=/tocky
WORKDIR /tocky/app

EXPOSE 5000

CMD ["flask", "run"]

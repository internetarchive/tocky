FROM python:3.11

ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0

# Setup tesseract
RUN apt-get update \
    && apt-get install -y software-properties-common \
    && add-apt-repository -y ppa:alex-p/tesseract-ocr5 \
    && apt-get update \
    && apt-get install -y tesseract-ocr tesseract-ocr-eng

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry install --extras "app"

COPY ./app /app

EXPOSE 5000

CMD ["flask", "run"]

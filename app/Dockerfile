FROM python:3.11

RUN pip install poetry

ENV FLASK_APP=app.py \
    FLASK_RUN_HOST=0.0.0.0 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --only "app" --compile

COPY ./app /app

EXPOSE 5000

CMD ["flask", "run"]

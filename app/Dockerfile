FROM python:3.11

ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0

RUN pip install poetry

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --only "app" --compile

COPY ./app /app

EXPOSE 5000

CMD ["flask", "run"]

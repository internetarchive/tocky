FROM python:3.11

ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry install --extras "app"

COPY ./app /app

EXPOSE 5000

CMD ["flask", "run"]

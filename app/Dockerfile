FROM python:3.11-slim-bookworm

# Choose the OCR engines to install. Note installing these increases the image size
# drastically. The available options are "tesseract" and "easyocr", or both! E.g.
# ARG OCR_ENGINES="tesseract easyocr"
ARG OCR_ENGINES=""

# Config options to run in private environment
ARG PIP_INDEX_URL=""
ARG APT_MIRROR=""
ARG HTTPS_PROXY=""
ARG NO_PROXY=""

# Add the Tesseract OCR repository and install Tesseract OCR
RUN if [ -n "$APT_MIRROR" ]; then \
        echo "deb $APT_MIRROR/debian bookworm main contrib non-free" > /etc/apt/sources.list && \
        echo "deb $APT_MIRROR/debian bookworm-updates main contrib non-free" >> /etc/apt/sources.list && \
        echo "deb $APT_MIRROR/debian-security bookworm-security main contrib non-free" >> /etc/apt/sources.list && \
        # Debian repositories with frequent updates e.g.,
        # ${distro}-security, ${distro}-updates, and ${distro}-backports
        # have a short (one week) Valid-Until expiry
        # which conflicts with our practice of a local apt-mirror updating weekly
        echo 'Acquire::Check-Valid-Until "false";' > /etc/apt/apt.conf.d/99no-check-valid-until && \
        apt update -o Dir::Etc::sourcelist="sources.list" -o Dir::Etc::sourceparts="-" -o APT::Get::List-Cleanup="0"; \
    else \
        apt update; \
    fi \
    && if echo $OCR_ENGINES | grep -q tesseract; then \
        apt-get install -y tesseract-ocr tesseract-ocr-eng libopencv-dev; \
    fi \
    && apt-get clean

RUN pip install poetry==1.7.1

ENV POETRY_VIRTUALENVS_CREATE=false

WORKDIR /tocky

COPY pyproject.toml poetry.lock ./
RUN if [ -n "$PIP_INDEX_URL" ]; then \
        poetry source add private $PIP_INDEX_URL --default; \
    fi \
    && poetry install --extras "app $OCR_ENGINES" --compile
COPY ./ /tocky

ENV PYTHONPATH=/tocky
WORKDIR /tocky

EXPOSE 5000

CMD ["poetry", "run", "uvicorn", "app.app:app", "--host", "0.0.0.0", "--port", "5000"]

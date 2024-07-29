FROM python:3.11

ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0

# Setup tesseract
RUN add-apt-repository -y ppa:alex-p/tesseract-ocr5 \
    && apt-get update \
    && apt-get install -y tesseract-ocr tesseract-ocr-eng

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY . /app

EXPOSE 5000

CMD ["flask", "run"]

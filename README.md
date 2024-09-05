# Tocky

A tool to extract table of contents data from Internet Archive books.

## Phases

- **Detector**: Responsible for finding the pages that contain the table of
  contents in the book.
- **Extractor**: Given the pages containing the table of contents, this phase is
  responsible for converting those pages to a structured format.

## Installation

```sh
# You will need to use poetry in order to install the dependencies
pip install poetry
poetry install tocky
```

Dependency groups:

- `poetry install tocky --with tesseract` to also install Tesseract dependencies
- `poetry install tocky --with easyocr` to also install Azure dependencies
- `poetry install tocky --with app` to also install the flask UI/web app


## Pipeline

A task moves through the pipeline in the following order:

```mermaid
flowchart TD
    A(To Detect)
    --> B(Detecting)
    --> C(To Extract)
    --> D(Extracting)
    --> E(To Review)
    --> F(Reviewing)
    --> G(Done)
```

## Development

Activate the virtual environment:

```bash
source .venv/Scripts/activate
```

Running tests:

```bash
pytest tests
```

Useful snippet for doing DB operations:

```py
import app
from contextlib import closing

with closing(app.get_conn()) as conn:
    with closing(conn.cursor()) as cur:
        cur.execute("""
            SELECT * FROM toc_queue
            WHERE state = 'Reviewing'
        """)
        conn.commit()
```

Removing a book from the queue:

```py
import app
from contextlib import closing

with closing(app.get_conn()) as conn:
    with closing(conn.cursor()) as cur:
        cur.execute("""
            DELETE FROM toc_queue
            WHERE id = '847'
        """)
        conn.commit()
```

## Options

### OCR Engine

Tocky supports books with existing OCR data, with the option to redo the OCR
using a custom engine. Each engine has its own pros and cons:

| Engine    | CPU? | Self-hosted? | Lines? | Paragraphs? | Columns? | Handles leader dots? | Handles single pagenums? | Confidence scores? |
| --------- | ---- | ------------ | ------ | ----------- | -------- | -------------------- | ------------------------ | ------------------ |
| Tesseract | ✅   | ✅           | ✅     | ✅          | ✅       | ❌                   | Rarely                   | ✅                 |
| EasyOCR   | ❌   | ✅           | ❌     | ❌          | ❌       | ✅                   | Sometimes                | ❔                 |
| Azure     | ✅   | ❌           | ✅     | ❌          | ❔       | ❔                   | ❔                       | ✅                 |


from fastapi import FastAPI, Request, Depends, HTTPException, status, Query, Body
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from typing import Optional, cast
import json
import sqlite3
from pathlib import Path
from tocky import EXTRACTORS_BY_NAME
from tocky.bulk_processor import TockyOptionsError, build_phase_from_options, process_from_options
from tocky.env import get_env
from tocky.extractor.ai_extractor import AiExtractor
from tocky.ocr import get_supported_engines
from tocky.utils import get_tocky_version
from tocky.utils.ia import get_ia_metadata_field, get_page_image
from jinja2 import Environment, FileSystemLoader

env = get_env()

class DbContext:
    def __init__(self):
        self.conn = sqlite3.connect(env.TOCKY_QUEUE_DB_PATH)
        self.conn.row_factory = sqlite3.Row

    def __enter__(self):
        self.cursor = self.conn.cursor()
        self.cursor.execute("PRAGMA temp_store = MEMORY;")
        self.cursor.execute("PRAGMA cache_size = 10000;")
        self.cursor.execute("PRAGMA journal_mode = WAL;")
        return self.conn, self.cursor

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cursor.close()
        self.conn.close()

def init_db():
    init_sql = '''
        CREATE TABLE toc_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            state VARCHAR(255) NOT NULL,
            assignee VARCHAR(255),
            record JSON NOT NULL
        );

        CREATE INDEX idx_q_created ON toc_queue (created);
        CREATE INDEX idx_q_state ON toc_queue (state);
    '''
    with DbContext() as (conn, cur):
        # Run init sql if table does not exist
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='toc_queue'")
        result = cur.fetchone()
        if not result:
            cur.executescript(init_sql)


init_db()


app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Jinja2 templates
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / 'templates'
STATIC_DIR = BASE_DIR / 'static'

jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    variable_start_string='[[',
    variable_end_string=']]',
    block_start_string='[%',
    block_end_string='%]',
    comment_start_string='[#',
    comment_end_string='#]',
)
jinja_env.globals['TOCKY_APPLICATION_ROOT'] = env.TOCKY_APPLICATION_ROOT
jinja_env.globals['TOCKY_VERSION'] = get_tocky_version()
jinja_env.globals['TOCKY_PUBLIC_CONFIG_JSON'] = json.dumps({
    'APPLICATION_ROOT': env.TOCKY_APPLICATION_ROOT,
    'OCR_ENGINES': get_supported_engines(),
})
templates = Jinja2Templates(env=jinja_env)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

def authenticate(request: Request):
    api_key = request.headers.get('X-API-Key') or request.cookies.get('TOCKY_API_KEY')
    if api_key in [env.TOCKY_SERVER_KEY, env.TOCKY_USER_KEY]:
        return True
    else:
        raise HTTPException(status_code=401, detail='Invalid API key')

def requires_key(_ = Depends(authenticate)):
    pass

@app.get('/pop')
def pop(assignee: Optional[str] = Query(None), last_id: int = Query(0), _=Depends(requires_key)):
    with DbContext() as (conn, cur):
        result = cur.execute("""
            SELECT * FROM toc_queue
            WHERE state = 'To Review' AND id > ?
            ORDER BY created ASC
            LIMIT 1
        """, (last_id,))
        row = result.fetchone()
        if row:
            cur.execute("""
                UPDATE toc_queue
                SET state = 'Reviewing',
                    assignee = ?
                WHERE id = ?
            """, (assignee, row['id']))
            conn.commit()
            row_dict = dict(zip(row.keys(), row))
            row_dict['record'] = json.loads(row_dict['record'])
            return row_dict
        else:
            return None

@app.post('/update/{id}')
def update(id: int, content: dict = Body(...), assignee: Optional[str] = Query(None), _=Depends(requires_key)):
    """Reads the record from the content body and writes it back to sqlite"""
    state = content.get('state', 'Done')
    set_requests = [
        'state = ?',
        'record = ?',
    ]
    set_params = [state, json.dumps(content)]
    if assignee:
        set_requests.append('assignee = ?')
        set_params.append(assignee)
    with DbContext() as (conn, cur):
        cur.execute(f"""
            UPDATE toc_queue
            SET {", ".join(set_requests)}
            WHERE id = ?
        """, (*set_params, id))
        conn.commit()
        return {"success": True}

@app.put('/push')
def push(content: dict = Body(...), _=Depends(requires_key)):
    """Reads a record from the content body and adds a new row to sqlite"""
    state = content.get('state', 'To Review')
    with DbContext() as (conn, cur):
        result = cur.execute("""
            INSERT INTO toc_queue (state, record)
            VALUES (?, ?)
        """, (state, json.dumps(content),))
        conn.commit()
        return {"success": True, "id": result.lastrowid}

@app.get('/list', response_class=HTMLResponse)
def list_view(request: Request):
    return templates.TemplateResponse('list.html', {"request": request})

@app.get('/api/list')
def api_list(request: Request, limit: int = Query(10), offset: int = Query(0), sort: str = Query('-created')):
    direction = 'DESC' if sort[0] == '-' else 'ASC'
    sort_field = sort.lstrip('-')
    if sort_field not in ['id', 'created', 'state']:
        return JSONResponse({'success': False, 'message': 'Invalid sort field'}, status_code=400)
    where_clauses = []
    params = []
    for list_field in ['id', 'state', 'assignee', 'record.status', 'record.human_validation']:
        arg_val = request.query_params.get(list_field)
        if arg_val:
            filter_list = arg_val.split('|')
            if list_field == 'id':
                filter_list = [int(x) for x in filter_list]
            field_parts = list_field.split('.')
            sub_fields = field_parts[1:]
            db_field = field_parts[0]
            if sub_fields:
                db_field += ' ->> ?'
            where_clauses.append(f'{db_field} IN ({",".join(["?"] * len(filter_list))})')
            params.extend(sub_fields)
            params.extend(filter_list)
    with DbContext() as (conn, cur):
        result = cur.execute(f"""
            SELECT * FROM toc_queue
            {"WHERE " + " AND ".join(where_clauses) if where_clauses else ""}
            ORDER BY {sort_field} {direction}
            LIMIT ? OFFSET ?
        """, (*params, limit, offset))
        return [
            {
                **dict(row),
                'record': json.loads(row['record']),
            }
            for row in result.fetchall()
        ]

@app.get('/api/extractor/build_prompt')
def api_extractor_prompt(id: int = Query(...)):
    with DbContext() as (conn, cur):
        cur.execute("SELECT record FROM toc_queue WHERE id = ?", (id,))
        row = cur.fetchone()
        if not row:
            return JSONResponse({'success': False, 'message': 'ID not found'}, status_code=404)
        record = json.loads(row['record'])
    extractor_type = record['extractor']['type']
    if extractor_type != 'ai_extractor':
        return JSONResponse({'success': False, 'message': 'Extractor type is not AI Extractor'}, status_code=400)
    extractor = build_phase_from_options(EXTRACTORS_BY_NAME, extractor_type, record['extractor']['options'])
    extractor = cast(AiExtractor, extractor)
    return {
        'success': True,
        'messages': extractor.build_prompt(
            extractor.chunk_ocr_text(record['toc_raw_ocr'])[0],
            book_title=get_ia_metadata_field(record['input_book']['ia_id'], '/metadata/title'),
            prev_toc=None,
        ),
    }

@app.get('/stats')
def stats():
    with DbContext() as (conn, cur):
        result = cur.execute("""
            SELECT state, count(*) as count FROM toc_queue
            GROUP BY state
        """)
        return [
            {
                **dict(row),
            }
            for row in result.fetchall()
        ]

@app.get('/review', response_class=HTMLResponse)
def review(request: Request):
    return templates.TemplateResponse('review.html', {"request": request})

@app.get('/review/{id}', response_class=HTMLResponse)
def review_single(id: int, request: Request):
    return templates.TemplateResponse('review.html', {"request": request, "id": id})

@app.get('/submit', response_class=HTMLResponse)
def submit(request: Request):
    return templates.TemplateResponse('submit.html', {"request": request})

def generate_stream(server_response):
    for chunk in server_response.iter_content(chunk_size=4096):
        yield chunk

@app.get('/ia_img')
def ia_img(id: str = Query(...), leaf: int = Query(...), _=Depends(requires_key)):
    if leaf > 30 or leaf < 0:
        raise HTTPException(status_code=400, detail='Leaf number must be between 0 and 30')
    def stream():
        yield from generate_stream(get_page_image(id, leaf, ext='jpg', reduce=3, quality=20, stream=True))
    return StreamingResponse(stream(), media_type='image/jpeg')

@app.get('/ia_toc_img')
def ia_toc_img(id: int = Query(...), index: int = Query(...), _=Depends(requires_key)):
    if not id or id < 0:
        return JSONResponse({'success': False, 'message': 'TOC ID is required'}, status_code=400)
    if index is None:
        return JSONResponse({'success': False, 'message': 'Index is required'}, status_code=400)
    with DbContext() as (conn, cur):
        cur.execute("SELECT record FROM toc_queue WHERE id = ?", (id,))
        row = cur.fetchone()
        if not row:
            return JSONResponse({'success': False, 'message': 'TOC ID not found'}, status_code=404)
        record = json.loads(row['record'])
        ia_id = record['ocaid']
        detected_toc = record['detected_toc']
        if not detected_toc:
            return JSONResponse({'success': False, 'message': 'TOC not detected'}, status_code=404)
        detected_toc = detected_toc[0:10]
        if not(-2 <= index <= len(detected_toc) + 2):
            return JSONResponse({'success': False, 'message': 'Index out of range'}, status_code=400)
        if index < 0:
            leaf_num = detected_toc[0] + index
        elif index < len(detected_toc):
            leaf_num = detected_toc[index]
        else:
            leaf_num = detected_toc[-1] + (index - len(detected_toc))
        def stream():
            yield from generate_stream(get_page_image(ia_id, leaf_num, ext='jpg', reduce=2, quality=70, stream=True))
        return StreamingResponse(stream(), media_type='image/jpeg')

@app.post('/submit')
def submit_post(submit_options: dict = Body(...), _=Depends(requires_key)):
    try:
        state = process_from_options(submit_options, push=True)
        return state.to_response_dict()
    except TockyOptionsError as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=400)

import asyncio
from contextlib import asynccontextmanager
from fastapi import BackgroundTasks, FastAPI, Request, Depends, HTTPException, Query, Body
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi import APIRouter
from typing import Optional, cast
import json
from pathlib import Path
from app.db.utils import DbContext, clear_dead_jobs, init_db, db_select_from_params
from app.worker import process_batches
from tocky import EXTRACTORS_BY_NAME
from tocky.batches import Batch
from tocky.bulk_processor import TockyOptionsError, build_phase_from_options, process_from_options
from tocky.env import get_env
from tocky.extractor.ai_extractor import AiExtractor
from tocky.ocr import get_supported_engines
from tocky.utils import get_tocky_version
from tocky.utils.ia import get_ia_metadata_field, get_page_image
from jinja2 import Environment, FileSystemLoader, pass_context

env = get_env()

init_db()


@asynccontextmanager
async def lifespan(app: FastAPI):
    clear_dead_jobs()
    task = asyncio.create_task(process_batches())
    yield
    print("App or worker is shutting down...")
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        print("Background task cancelled successfully.")

app = FastAPI(lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # FIXME
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

def authenticate(request: Request):
    api_key = request.headers.get('X-API-Key') or request.cookies.get('TOCKY_API_KEY')
    if api_key in [env.TOCKY_SERVER_KEY, env.TOCKY_USER_KEY]:
        return True
    else:
        raise HTTPException(status_code=401, detail='Invalid API key')

def requires_key(_ = Depends(authenticate)):
    pass

# Create a router with prefix from TOCKY_APPLICATION_ROOT
tocky_router = APIRouter(prefix=env.TOCKY_APPLICATION_ROOT)

@pass_context
def url_for(context: dict, name: str, /, **path_params):
    # Overwrite stock FastAPI url_for to use the Tocky public URL scheme
    # Otherwise this is annoying and requires redirects/oof.
    result = context['request'].url_for(name, **path_params)
    # Replace the scheme to match the environment's public URL
    return result.replace(scheme=env.TOCKY_PUBLIC_URL_SCHEME)

jinja_env.globals['url_for'] = url_for

app.mount(env.TOCKY_APPLICATION_ROOT + "/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@tocky_router.get('/pop')
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

@tocky_router.post('/update/{id}')
def update(background_tasks: BackgroundTasks, id: int, content: dict = Body(...), assignee: Optional[str] = Query(None), _=Depends(requires_key)):
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
        background_tasks.add_task(process_batches)
        return {"success": True}

@tocky_router.put('/push')
def push(content: dict = Body(...), _=Depends(requires_key)):
    """Reads a record from the content body and adds a new row to sqlite"""
    state = content.get('state', 'To Review')
    process_id_str = content['process_id_str']
    batch_id = content.get('batch_id', None)
    with DbContext() as (conn, cur):
        result = cur.execute("""
            INSERT INTO toc_queue (process_id_str, batch_id, state, record)
            VALUES (?, ?, ?, ?)
        """, (process_id_str, batch_id, state, json.dumps(content),))
        conn.commit()
        return {"success": True, "id": result.lastrowid}

@tocky_router.get('/batches', response_class=HTMLResponse)
def batches(request: Request):
    return templates.TemplateResponse('batches.html', {"request": request})

@tocky_router.get('/list', response_class=HTMLResponse)
def list_view(request: Request):
    return templates.TemplateResponse('list.html', {"request": request})

@tocky_router.get('/api/list')
def api_list(request: Request, limit: int = Query(10), offset: int = Query(0), sort: str = Query('-created')):
    return db_select_from_params(
        table='toc_queue',
        filter_fields=('id', 'state', 'batch_id', 'assignee', 'record.status', 'record.human_validation'),
        sort_fields=('id', 'created', 'state', 'batch_id', 'assignee'),
        limit=limit,
        offset=offset,
        sort=sort,
        request=request,
    )

@tocky_router.get('/api/batches')
def api_batches(request: Request, limit: int = Query(10), offset: int = Query(0), sort: str = Query('-created')):
    return db_select_from_params(
        table='batches',
        filter_fields=('id', 'state', 'creator'),
        sort_fields=('id', 'created', 'state'),
        limit=limit,
        offset=offset,
        sort=sort,
        request=request,
    )

@tocky_router.get('/api/extractor/build_prompt')
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

@tocky_router.get('/stats')
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

@tocky_router.get('/review', response_class=HTMLResponse)
def review(request: Request):
    return templates.TemplateResponse('review.html', {"request": request})

@tocky_router.get('/review/{id}', response_class=HTMLResponse)
def review_single(id: int, request: Request):
    return templates.TemplateResponse('review.html', {"request": request, "id": id})

@tocky_router.get('/submit', response_class=HTMLResponse)
def submit(request: Request):
    return templates.TemplateResponse('submit.html', {"request": request})

def generate_stream(server_response):
    for chunk in server_response.iter_content(chunk_size=4096):
        yield chunk

@tocky_router.get('/ia_img')
def ia_img(id: str = Query(...), leaf: int = Query(...), _=Depends(requires_key)):
    if leaf > 30 or leaf < 0:
        raise HTTPException(status_code=400, detail='Leaf number must be between 0 and 30')
    def stream():
        yield from generate_stream(get_page_image(id, leaf, ext='jpg', reduce=3, quality=20, stream=True))
    return StreamingResponse(stream(), media_type='image/jpeg')

@tocky_router.get('/ia_toc_img')
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

@tocky_router.post('/submit')
def submit_post(background_tasks: BackgroundTasks, background: bool = Query(False), submit_options: dict = Body(...), _=Depends(requires_key)):
    if submit_options.get('batch'):
        batch = Batch.from_submit_input(submit_options)
        batch.limit = min(batch.get_total(), cast(int, submit_options['batch']['max_limit']))
        with DbContext() as (conn, cur):
            cur.execute(*batch.to_sql())
            conn.commit()
            batch_id = cur.lastrowid
            background_tasks.add_task(process_batches)
            return {"success": True, "batch_id": batch_id}

    if background:
        background_tasks.add_task(
            process_from_options,
            submit_options,
            push=True,
        )
        return JSONResponse({'success': True, 'message': 'Batch processing started'}, status_code=202)
    else:
        try:
            state = process_from_options(submit_options, push=True)
            return state.to_response_dict()
        except TockyOptionsError as e:
            return JSONResponse({'success': False, 'message': str(e)}, status_code=400)

app.include_router(tocky_router)

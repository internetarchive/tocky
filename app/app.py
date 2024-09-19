import functools
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import json
import sqlite3
from tocky.bulk_processor import TockyOptionsError, process_from_options, process_ia_book
from tocky.env import get_env
from tocky.utils.ia import get_page_image

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


app = Flask(__name__)
app.config['env'] = env
app.config['SERVER_NAME'] = env.TOCKY_SERVER_NAME
app.config['APPLICATION_ROOT'] = env.TOCKY_APPLICATION_ROOT
app.config['PREFERRED_URL_SCHEME'] = env.TOCKY_PREFERRED_URL_SCHEME
CORS(app)

# Configure Jinja to use different delimiters to avoid conflicts with Vue
app.jinja_env.variable_start_string = '[['
app.jinja_env.variable_end_string = ']]'
app.jinja_env.block_start_string = '[%'
app.jinja_env.block_end_string = '%]'
app.jinja_env.comment_start_string = '[#'
app.jinja_env.comment_end_string = '#]'

# Pre-render the templates; they're effectively static, save for some `config` variables
with app.app_context():
    static_templates = {
        'review.html': render_template('review.html'),
        'submit.html': render_template('submit.html'),
        'list.html': render_template('list.html'),
    }

def render_static_template(template_name):
    # Check if running in reload mode
    if app.debug:
        return render_template(template_name)
    else:
        return static_templates[template_name]

def authenticate():
    # Check header for api key
    api_key = request.headers.get('X-API-Key') or request.cookies.get('TOCKY_API_KEY')
    if api_key in [env.TOCKY_SERVER_KEY, env.TOCKY_USER_KEY]:
        return True
    else:
        return False

# Create a authenticate decorator
def requires_key(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not authenticate():
            return jsonify({'success': False, 'message': 'Invalid API key'}), 401
        return f(*args, **kwargs)
    return decorated

@app.route('/pop', methods=['GET'])
@requires_key
def pop():
    assignee = request.args.get('assignee')
    last_id = request.args.get('last_id', type=int) or 0

    with DbContext() as (conn, cur):
        # Execute the parameterized query
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
            return jsonify(row_dict)
        else:
            return jsonify(None)

@app.route('/update/<int:id>', methods=['POST'])
@requires_key
def update(id: int):
    """Reads the record from the content body and writes it back to sqlite"""
    content = request.get_json()
    state = content.get('state', 'Done')
    
    set_requests = [
        'state = ?',
        'record = ?',
    ]
    set_params = [state, json.dumps(content)]
    if assignee := request.args.get('assignee'):
        set_requests.append('assignee = ?')
        set_params.append(assignee)


    with DbContext() as (conn, cur):
        # Execute the parameterized query
        cur.execute(f"""
            UPDATE toc_queue
            SET {", ".join(set_requests)}
            WHERE id = ?
        """, (*set_params, id))
        conn.commit()
        return jsonify({'success': True})


@app.route('/push', methods=['PUT'])
@requires_key
def push():
    """Reads a record from the content body and adds a new row to sqlite"""
    content = request.get_json()
    state = content.get('state', 'To Review')

    with DbContext() as (conn, cur):
        # Execute the parameterized query
        result = cur.execute("""
            INSERT INTO toc_queue (state, record)
            VALUES (?, ?)
        """, (state, json.dumps(content),))
        conn.commit()
        return jsonify({'success': True, 'id': result.lastrowid})


@app.route('/list', methods=['GET'])
def list():
    """Reads the limit and offset from the query string and returns a list of records"""
    return render_static_template('list.html')


@app.route('/api/list', methods=['GET'])
def api_list():
    limit = request.args.get('limit', 10, type=int)
    offset = request.args.get('offset', 0, type=int)

    where_clauses = []
    params = []

    for list_field in ['id', 'state', 'assignee', 'record.status', 'record.human_validation']:
        if arg_val := request.args.get(list_field):
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
        # Execute the parameterized query
        result = cur.execute(f"""
            SELECT * FROM toc_queue
            {"WHERE " + " AND ".join(where_clauses) if where_clauses else ""}
            ORDER BY created DESC
            LIMIT ? OFFSET ?
        """, (*params, limit, offset))
        return jsonify([
            {
                **dict(row),
                'record': json.loads(row['record']),
            }
            for row in result.fetchall()
        ])

@app.route('/stats', methods=['GET'])
def stats():
    with DbContext() as (conn, cur):
        result = cur.execute("""
            SELECT state, count(*) as count FROM toc_queue
            GROUP BY state
        """)
        return jsonify([
            {
                **dict(row),
            }
            for row in result.fetchall()
        ])

@app.route('/review', methods=['GET'])
def review():
    return render_static_template('review.html')

@app.route('/review/<int:id>', methods=['GET'])
def review_single(id: int):
    return render_static_template('review.html')

@app.route('/submit', methods=['GET'])
def submit():
    return render_static_template('submit.html')

def generate_stream(server_response):
    for chunk in server_response.iter_content(chunk_size=4096):
        yield chunk

@app.route('/ia_img', methods=['GET'])
@requires_key
def ia_img():
    """Serves a low res image from IA"""
    ia_id = request.args.get('id')
    leaf_num = request.args.get('leaf', type=int)

    if not ia_id:
        return jsonify({'success': False, 'message': 'IA ID is required'}), 400

    if leaf_num is None:
        return jsonify({'success': False, 'message': 'Leaf number is required'}), 400

    if leaf_num > 30 or leaf_num < 0:
        return jsonify({'success': False, 'message': 'Leaf number must be between 0 and 30'}), 400

    return Response(
        stream_with_context(generate_stream(get_page_image(ia_id, leaf_num, ext='jpg', reduce=3, quality=20, stream=True))),
        content_type='image/jpeg',
    )

@app.route('/ia_toc_img', methods=['GET'])
@requires_key
def ia_toc_img():
    toc_id = request.args.get('id', type=int)
    index = request.args.get('index', type=int)

    if not toc_id or toc_id < 0:
        return jsonify({'success': False, 'message': 'TOC ID is required'}), 400
    
    if index is None:
        return jsonify({'success': False, 'message': 'Index is required'}), 400

    with DbContext() as (conn, cur):
        cur.execute("SELECT record FROM toc_queue WHERE id = ?", (toc_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({'success': False, 'message': 'TOC ID not found'}), 404

        record = json.loads(row['record'])

        ia_id = record['ocaid']
        detected_toc = record['detected_toc']

        if not detected_toc:
            return jsonify({'success': False, 'message': 'TOC not detected'}), 404

        # Truncate to max 10 entries
        detected_toc = detected_toc[0:10]

        if not(-2 <= index <= len(detected_toc) + 2):
            return jsonify({'success': False, 'message': 'Index out of range'}), 400
        
        if index < 0:
            leaf_num = detected_toc[0] + index
        elif index < len(detected_toc):
            leaf_num = detected_toc[index]
        else:
            leaf_num = detected_toc[-1] + (index - len(detected_toc))

        return Response(
            stream_with_context(generate_stream(get_page_image(ia_id, leaf_num, ext='jpg', reduce=2, quality=70, stream=True))),
            content_type='image/jpeg',
        )

@app.route('/submit', methods=['POST'])
@requires_key
def submit_post():
    # Read the content from the request
    submit_options = request.get_json()

    try:
        state = process_from_options(submit_options, push=True)
        return jsonify(state.to_response_dict())
    except TockyOptionsError as e:
        return jsonify({'success': False, 'message': str(e)}), 400

if __name__ == '__main__':
    if not env.TOCKY_SERVER_KEY or not env.TOCKY_USER_KEY:
        raise ValueError('TOCKY_SERVER_KEY environment variable must be set')

    app.run(host='0.0.0.0', port=5000)

from contextlib import closing
import dataclasses
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import json
import sqlite3
import os
from tocky.bulk_processor import process_ia_book
from tocky.detector import AbstractDetector
from tocky.detector.ai_vision_detector import AiVisionDetector
from tocky.detector.ocr_detector import OcrDetector
from tocky.detector.manual_detector import ManualDetector
from tocky.env import get_env
from tocky.extractor.ai_extractor import AiExtractor
from tocky.extractor.ai_vision_extractor import AiVisionExtractor

env = get_env()

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(env.TOCKY_QUEUE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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
    with closing(get_conn()) as conn:
        with closing(conn.cursor()) as cur:
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


@app.route('/pop', methods=['GET'])
def pop():
    # Check header for api key
    api_key = request.headers.get('X-API-Key')
    if api_key != env.TOCKY_SERVER_KEY:
        return jsonify({'success': False, 'message': 'Invalid API key'}), 401

    assignee = request.args.get('assignee')
    with closing(get_conn()) as conn:
        with closing(conn.cursor()) as cur:
            # Execute the parameterized query
            result = cur.execute("""
                SELECT * FROM toc_queue
                WHERE state = 'To Review'
                ORDER BY created ASC
                LIMIT 1
            """)
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
def update(id: int):
    """Reads the record from the content body and writes it back to sqlite"""
    # Check header for api key
    api_key = request.headers.get('X-API-Key')
    if api_key != env.TOCKY_SERVER_KEY:
        return jsonify({'success': False, 'message': 'Invalid API key'}), 401

    content = request.get_json()
    state = content.get('state', 'Done')
    with closing(get_conn()) as conn:
        with closing(conn.cursor()) as cur:
            # Execute the parameterized query
            cur.execute("""
                UPDATE toc_queue
                SET state = ?,
                    record = ?
                WHERE id = ?
            """, (state, json.dumps(content), id))
            conn.commit()
            return jsonify({'success': True})


@app.route('/push', methods=['PUT'])
def push():
    """Reads a record from the content body and adds a new row to sqlite"""
    # Check header for api key
    api_key = request.headers.get('X-API-Key')
    if api_key != env.TOCKY_SERVER_KEY:
        return jsonify({'success': False, 'message': 'Invalid API key'}), 401

    content = request.get_json()
    state = content.get('state', 'To Review')

    with closing(get_conn()) as conn:
        with closing(conn.cursor()) as cur:
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
    return static_templates['list.html']


@app.route('/api/list', methods=['GET'])
def api_list():
    limit = request.args.get('limit', 10, type=int)
    offset = request.args.get('offset', 0, type=int)

    where_clauses = []
    params = []

    if (_id := request.args.get('id', None, type=int)) is not None:
        where_clauses.append('id = ?')
        params.append(_id)

    if state := request.args.get('state'):
        where_clauses.append('state = ?')
        params.append(state)
    
    if assignee := request.args.get('assignee'):
        where_clauses.append('assignee = ?')
        params.append(assignee)

    with closing(get_conn()) as conn:
        with closing(conn.cursor()) as cur:
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
    with closing(get_conn()) as conn:
        with closing(conn.cursor()) as cur:
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
    return static_templates['review.html']

@app.route('/review/<int:id>', methods=['GET'])
def review_single(id: int):
    return static_templates['review.html']

@app.route('/submit', methods=['GET'])
def submit():
    return static_templates['submit.html']

@app.route('/submit', methods=['POST'])
def submit_post():
    # Check header for api key
    api_key = request.headers.get('X-API-Key')
    if api_key != env.TOCKY_SERVER_KEY:
        return jsonify({'success': False, 'message': 'Invalid API key'}), 401

    # Read the content from the request
    submit_options = request.get_json()
    
    if not submit_options['input_book']['ia_id']:
        return jsonify({'success': False, 'message': 'IA ID is required'}), 400

    ia_id = submit_options['input_book']['ia_id']

    DETECTORS: dict[str, type[AbstractDetector]] = {
        'ocr_detector': OcrDetector,
        'ai_vision_detector': AiVisionDetector,
        'manual_detector': ManualDetector,
    }

    # Set up detector
    DETECTOR_CLS = DETECTORS.get(submit_options['detector']['type'])
    if not DETECTOR_CLS:
        return jsonify({'success': False, 'message': f'Invalid detector type: {submit_options["detector"]["type"]}'}), 400

    detector = DETECTOR_CLS()
    try:
        detector.P = dataclasses.replace(detector.P, **submit_options['detector']['options'])
    except TypeError as e:
        # TODO: This will not error if things are set to the wrong type
        return jsonify({'success': False, 'message': f'Invalid detector options: {e}'}), 400

    # Set up extractor
    EXTRACTORS = {
        'ai_extractor': AiExtractor,
        'ai_vision_extractor': AiVisionExtractor,
    }

    # Run extractor
    EXTRACTOR_CLS = EXTRACTORS.get(submit_options['extractor']['type'])
    if not EXTRACTOR_CLS:
        return jsonify({'success': False, 'message': f'Invalid extractor type: {submit_options["extractor"]["type"]}'}), 400

    extractor = EXTRACTOR_CLS()
    try:
        extractor.P = dataclasses.replace(extractor.P, **submit_options['extractor']['options'])
    except TypeError as e:
        # TODO: This will not error if things are set to the wrong type
        return jsonify({'success': False, 'message': f'Invalid extractor options: {e}'}), 400
    # Share cache
    extractor.S = detector.S

    # Now let's run some stuff!
    detector.debug = False    
    state = process_ia_book(ia_id, detector, extractor, push=True)


    return jsonify({
        'success': (
            state.detector_result
            and state.detector_result.success
            and state.extractor_result
            and state.extractor_result.success
        ),
        'options': {
            'input_book': submit_options['input_book'],
            'detector': {
                'type': submit_options['detector']['type'],
                'options': detector.P.__dict__,
            },
            'extractor': {
                'type': submit_options['extractor']['type'],
                'options': extractor.P.__dict__,
            },
        },
        'results': {
            'detector': state.detector_result.to_dict() if state.detector_result else None,
            'extractor': state.extractor_result.to_dict() if state.extractor_result else None,
        }
    })

if __name__ == '__main__':
    if not env.TOCKY_SERVER_KEY:
        raise ValueError('TOCKY_SERVER_KEY environment variable must be set')

    app.run(host='0.0.0.0', port=5000)

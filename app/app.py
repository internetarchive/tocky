from contextlib import closing
from dataclasses import dataclass
import dataclasses
from time import time
from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import sqlite3
import os
from tocky.detector.ai_detector import AiImageDetector
from tocky.detector.ocr_detector import OcrDetector

DB_FILE = "/data/database.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
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
CORS(app)

@app.route('/pop', methods=['GET'])
def pop():
    # Check header for api key
    api_key = request.headers.get('X-API-Key')
    if api_key != os.environ.get('API_KEY'):
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
    if api_key != os.environ.get('API_KEY'):
        return jsonify({'success': False, 'message': 'Invalid API key'}), 401

    content = request.get_json()
    with closing(get_conn()) as conn:
        with closing(conn.cursor()) as cur:
            # Execute the parameterized query
            cur.execute("""
                UPDATE toc_queue
                SET state = 'Done',
                    record = ?
                WHERE id = ?
            """, (json.dumps(content), id))
            conn.commit()
            return jsonify({'success': True})


@app.route('/push', methods=['PUT'])
def push():
    # Check header for api key
    api_key = request.headers.get('X-API-Key')
    if api_key != os.environ.get('API_KEY'):
        return jsonify({'success': False, 'message': 'Invalid API key'}), 401

    """Reads a record from the content body and adds a new row to sqlite"""
    content = request.get_json()
    with closing(get_conn()) as conn:
        with closing(conn.cursor()) as cur:
            # Execute the parameterized query
            cur.execute("""
                INSERT INTO toc_queue (state, record)
                VALUES ('To Review', ?)
            """, (json.dumps(content),))
            conn.commit()
            return jsonify({'success': True})


@app.route('/list', methods=['GET'])
def list():
    """Reads the limit and offset from the query string and returns a list of records"""
    limit = request.args.get('limit', 10, type=int)
    offset = request.args.get('offset', 0, type=int)

    with closing(get_conn()) as conn:
        with closing(conn.cursor()) as cur:
            # Execute the parameterized query
            result = cur.execute("""
                SELECT * FROM toc_queue
                ORDER BY created DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))
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
def root():
    # Render the Vue.js frontend
    return app.send_static_file('review.html')

@app.route('/submit', methods=['GET'])
def submit():
    return app.send_static_file('submit.html')




@app.route('/submit', methods=['POST'])
def submit_post():
    # Check header for api key
    api_key = request.headers.get('X-API-Key')
    if api_key != os.environ.get('API_KEY'):
        return jsonify({'success': False, 'message': 'Invalid API key'}), 401

    # Read the content from the request
    submit_options = request.get_json()
    
    if not submit_options['input_book']['ia_id']:
        return jsonify({'success': False, 'message': 'IA ID is required'}), 400

    ia_id = submit_options['input_book']['ia_id']

    DETECTORS = {
        'ocr_detector': OcrDetector,
        'ai_detector': AiImageDetector,
    }

    # Run detector
    DETECTOR_CLS = DETECTORS.get(submit_options['detector']['type'])
    if not DETECTOR_CLS:
        return jsonify({'success': False, 'message': f'Invalid detector type: {submit_options["detector"]["type"]}'}), 400
    
    detector = DETECTOR_CLS()
    try:
        detector.P = dataclasses.replace(detector.P, **submit_options['detector']['options'])
    except TypeError as e:
        # TODO: This will not error if things are set to the wrong type
        return jsonify({'success': False, 'message': f'Invalid detector options: {e}'}), 400
    
    detector.debug = False
    detector_start = time.time()
    try:
        detector_result = detector.detect(ia_id)
        detector_error = None
    except Exception as e:
        detector_error = e
        detector_result = None
    finally:
        detector_end = time.time()

    return jsonify({
        'success': bool(detector_error),
        'options': {
            'input_book': submit_options['input_book'],
            'detector': {
                'type': submit_options['detector']['type'],
                'options': detector.P.__dict__,
            },
            'extractor': {
                'type': submit_options['extractor']['type'],
                'options': submit_options['extractor']['options'],
            },
        },
        'results': {
            'detector': {
                'success': bool(detector_error),
                'time': detector_end - detector_start,
                'result': detector_result,
                'error': str(detector_error),
            },
        }
    })

if __name__ == '__main__':
    if not os.environ.get('API_KEY'):
        raise ValueError('API_KEY environment variable must be set')

    app.run(host='0.0.0.0', port=5000)

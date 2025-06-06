CREATE TABLE batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    creator VARCHAR(255),
    name VARCHAR(255),
    record JSON NOT NULL
);

CREATE TABLE toc_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    state VARCHAR(255) NOT NULL,
    creator VARCHAR(255),
    assignee VARCHAR(255),
    batch_id INTEGER,
    FOREIGN KEY (batch_id) REFERENCES batches(id)
    record JSON NOT NULL,
);

CREATE INDEX idx_q_created ON toc_queue (created);
CREATE INDEX idx_q_state ON toc_queue (state);
CREATE INDEX idx_q_batch_id ON toc_queue (batch_id);
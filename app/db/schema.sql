CREATE TABLE tocky_internals (
    key VARCHAR(255) PRIMARY KEY,
    value JSON NOT NULL
);

CREATE INDEX idx_internals_key ON tocky_internals (key);

CREATE TABLE batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    creator VARCHAR(255),
    name VARCHAR(255),
    state VARCHAR(255) NOT NULL DEFAULT 'Pending',
    record JSON NOT NULL
);

CREATE TABLE toc_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    state VARCHAR(255) NOT NULL,
    creator VARCHAR(255),
    assignee VARCHAR(255),
    batch_id INTEGER,
    -- PID with the create_time. E.g. "123#1749368288.537638"
    process_id_str VARCHAR(255),
    FOREIGN KEY (batch_id) REFERENCES batches(id)
    record JSON NOT NULL,
);

CREATE INDEX idx_q_created ON toc_queue (created);
CREATE INDEX idx_q_state ON toc_queue (state);
CREATE INDEX idx_q_batch_id ON toc_queue (batch_id);
CREATE INDEX idx_q_batch_id_state ON toc_queue (batch_id, state);

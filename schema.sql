CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT UNIQUE NOT NULL,
    ticket_type TEXT NOT NULL,
    subject TEXT NOT NULL,
    message TEXT NOT NULL,
    order_ref TEXT,
    delivery_date TEXT,
    requested_outcome TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS policy_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT UNIQUE NOT NULL,
    document_name TEXT NOT NULL,
    version TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('current', 'outdated')),
    effective_date TEXT
);

CREATE TABLE IF NOT EXISTS clauses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_document_id INTEGER NOT NULL,
    clause_number TEXT NOT NULL,
    title TEXT NOT NULL,
    text TEXT NOT NULL,
    FOREIGN KEY(policy_document_id) REFERENCES policy_documents(id)
);

CREATE TABLE IF NOT EXISTS suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL,
    draft TEXT NOT NULL,
    missing_information TEXT,
    model_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(ticket_id) REFERENCES tickets(id)
);

CREATE TABLE IF NOT EXISTS suggestion_clauses (
    suggestion_id INTEGER NOT NULL,
    clause_id INTEGER NOT NULL,
    rank INTEGER NOT NULL,
    similarity REAL,
    PRIMARY KEY(suggestion_id, clause_id),
    FOREIGN KEY(suggestion_id) REFERENCES suggestions(id),
    FOREIGN KEY(clause_id) REFERENCES clauses(id)
);

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    suggestion_id INTEGER NOT NULL,
    decision TEXT NOT NULL CHECK(decision IN ('accepted', 'edited', 'rejected')),
    final_text TEXT,
    rejection_reason TEXT,
    approval_needed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(suggestion_id) REFERENCES suggestions(id)
);

CREATE TABLE IF NOT EXISTS ticket_reopens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(ticket_id) REFERENCES tickets(id)
);

CREATE TABLE IF NOT EXISTS workflow_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    detail TEXT NOT NULL,
    simulated INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    FOREIGN KEY(decision_id) REFERENCES decisions(id)
);

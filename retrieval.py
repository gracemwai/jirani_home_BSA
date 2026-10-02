from typing import List, Dict
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from db import get_connection

def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())

def retrieve_current_clauses(ticket_text: str, top_k: int = 4) -> List[Dict]:

    conn = get_connection()
    rows = conn.execute("""
        SELECT
            c.id AS clause_id,
            c.clause_number,
            c.title,
            c.text,
            p.document_id,
            p.document_name,
            p.version,
            p.status
        FROM clauses c
        JOIN policy_documents p
          ON c.policy_document_id = p.id
        WHERE p.status = 'current'
    """).fetchall()
    conn.close()

    if not rows:
        return []

    records = [dict(r) for r in rows]
    corpus = [
        normalize(r["title"] + " " + r["text"])
        for r in records
    ]

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
    matrix = vectorizer.fit_transform(corpus)
    query = vectorizer.transform([normalize(ticket_text)])
    scores = cosine_similarity(query, matrix).ravel()

    for record, score in zip(records, scores):
        record["similarity"] = float(score)

    records.sort(key=lambda x: x["similarity"], reverse=True)

    # Don't present irrelevant zero-similarity clauses as applicable.
    return [r for r in records[:top_k] if r["similarity"] > 0]

def find_outdated_matches(ticket_text: str, top_k: int = 2) -> List[Dict]:
   
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            c.id AS clause_id,
            c.clause_number,
            c.title,
            c.text,
            p.document_name,
            p.version,
            p.status
        FROM clauses c
        JOIN policy_documents p
          ON c.policy_document_id = p.id
        WHERE p.status = 'outdated'
    """).fetchall()
    conn.close()

    if not rows:
        return []

    records = [dict(r) for r in rows]
    corpus = [normalize(r["title"] + " " + r["text"]) for r in records]
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
    matrix = vectorizer.fit_transform(corpus)
    query = vectorizer.transform([normalize(ticket_text)])
    scores = cosine_similarity(query, matrix).ravel()

    for record, score in zip(records, scores):
        record["similarity"] = float(score)

    records.sort(key=lambda x: x["similarity"], reverse=True)
    return [r for r in records[:top_k] if r["similarity"] > 0]

def get_ticket(ticket_db_id: int):
    conn = get_connection()
    row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_db_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def latest_accepted_decision(ticket_db_id: int):
    """Most recent accepted decision for a ticket, or None if never accepted."""
    conn = get_connection()
    row = conn.execute("""
        SELECT d.id, d.created_at
        FROM decisions d
        JOIN suggestions s ON d.suggestion_id = s.id
        WHERE s.ticket_id = ?
          AND d.decision = 'accepted'
        ORDER BY d.created_at DESC, d.id DESC
        LIMIT 1
    """, (ticket_db_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def latest_reopen(ticket_db_id: int):
    conn = get_connection()
    row = conn.execute("""
        SELECT id, note, created_at
        FROM ticket_reopens
        WHERE ticket_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
    """, (ticket_db_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def record_reopen(ticket_db_id: int, note: str = None):
    from datetime import datetime

    conn = get_connection()
    conn.execute(
        "INSERT INTO ticket_reopens (ticket_id, note, created_at) VALUES (?, ?, ?)",
        (ticket_db_id, note, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def is_accept_locked(ticket_db_id: int) -> bool:
    """
    An accepted ticket cannot be accepted again unless the customer has
    reopened it after that acceptance.
    """
    accepted = latest_accepted_decision(ticket_db_id)

    if not accepted:
        return False

    reopened = latest_reopen(ticket_db_id)

    if not reopened:
        return True

    # ISO timestamps compare correctly as strings. Equal timestamps mean the
    # reopen was recorded after the acceptance, so it counts as reopened.
    return reopened["created_at"] < accepted["created_at"]

def list_tickets():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM tickets ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]

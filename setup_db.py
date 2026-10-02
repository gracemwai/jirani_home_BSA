import json
from pathlib import Path
from datetime import datetime

from db import get_connection

BASE = Path(__file__).parent
SCHEMA = BASE / "schema.sql"
POLICIES = BASE / "policies.json"
TICKETS = BASE / "development_tickets.json"

def main():
    conn = get_connection()
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))

    existing = conn.execute("SELECT COUNT(*) AS n FROM policy_documents").fetchone()["n"]
    if existing == 0:
        policies = json.loads(POLICIES.read_text(encoding="utf-8"))

        for p in policies:
            conn.execute(
                """INSERT INTO policy_documents
                (document_id, document_name, version, status, effective_date)
                VALUES (?, ?, ?, ?, ?)""",
                (p["document_id"], p["document_name"], p["version"],
                 p["status"], p["effective_date"])
            )
            doc_id = conn.execute(
                "SELECT id FROM policy_documents WHERE document_id = ?",
                (p["document_id"],)
            ).fetchone()["id"]

            for c in p["clauses"]:
                conn.execute(
                    """INSERT INTO clauses
                    (policy_document_id, clause_number, title, text)
                    VALUES (?, ?, ?, ?)""",
                    (doc_id, c["clause_number"], c["title"], c["text"])
                )

    existing_tickets = conn.execute("SELECT COUNT(*) AS n FROM tickets").fetchone()["n"]
    if existing_tickets == 0:
        tickets = json.loads(TICKETS.read_text(encoding="utf-8"))
        now = datetime.now().isoformat(timespec="seconds")

        for t in tickets:
            conn.execute(
                """INSERT INTO tickets
                (ticket_id, ticket_type, subject, message, order_ref,
                 delivery_date, requested_outcome, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (t["ticket_id"], t["ticket_type"], t["subject"], t["message"],
                 t["order_ref"] or None, t["delivery_date"] or None,
                 t["requested_outcome"], now)
            )

    conn.commit()
    conn.close()
    print("Database ready:", BASE / "jirani.db")

if __name__ == "__main__":
    main()

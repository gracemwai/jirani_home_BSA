import os
import requests
from datetime import datetime

import streamlit as st

from db import DB_PATH, get_connection
from retrieval import (
    list_tickets,
    retrieve_current_clauses,
    find_outdated_matches,
    is_accept_locked,
    record_reopen,
)
from ai import generate_draft, missing_information


def load_env(path=".env"):
    if not os.path.exists(path):
        return

    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


load_env()

st.set_page_config(page_title="Jirani Home AI Policy Assistant", layout="wide")

st.title("Jirani Home — AI Policy Assistant")
st.caption("Prototype using fictional data • Human review required • No real customer messages are sent")

if not DB_PATH.exists():
    # Deployed instances start with no database file, so seed it on first run.
    from setup_db import main as setup_database

    setup_database()

tickets = list_tickets()

with st.sidebar:
    st.header("Prototype")
    st.info(
        "Current policy filtering is enforced in application code. "
        "Outdated policies are never supplied to the AI as citation candidates."
    )
    st.divider()
    st.write("**Scope:** returns, damaged-item tickets and supporting workflow.")
    st.write("**Data:** fictional.")
    st.write("**Send:** simulated only.")
    st.divider()
    if os.getenv("MAKE_WEBHOOK_URL"):
        st.caption("Make.com webhook: configured")
    else:
        st.warning("Make.com webhook: MAKE_WEBHOOK_URL is not set.")

    st.divider()
    st.subheader("Demo reset")
    confirm_reset = st.checkbox(
        "Clear decisions, drafts and reopen events",
        help="Keeps the tickets and policy documents. Use this to run the demo again from a clean state."
    )

    if st.button("Reset demo data", disabled=not confirm_reset):
        conn = get_connection()
        conn.execute("DELETE FROM workflow_runs")
        conn.execute("DELETE FROM decisions")
        conn.execute("DELETE FROM suggestion_clauses")
        conn.execute("DELETE FROM suggestions")
        conn.execute("DELETE FROM ticket_reopens")
        conn.commit()
        conn.close()

        st.session_state.draft = None
        st.session_state.sources = []
        st.session_state.missing = []
        st.session_state.model_name = None

        st.success("Demo data cleared. Tickets and policies are unchanged.")
        st.rerun()

ticket_labels = [f"{t['ticket_id']} — {t['subject']}" for t in tickets]
selected_label = st.sidebar.selectbox("Open ticket", ticket_labels)
selected_index = ticket_labels.index(selected_label)
ticket = tickets[selected_index]

st.subheader(ticket["subject"])

col1, col2 = st.columns(2)

with col1:
    st.write("**Ticket ID:**", ticket["ticket_id"])
    st.write("**Type:**", ticket["ticket_type"])
    st.write("**Customer message**")
    st.info(ticket["message"])

with col2:
    st.write("**Order reference:**", ticket["order_ref"] or "Unknown")
    st.write("**Delivery date:**", ticket["delivery_date"] or "Unknown")
    st.write("**Requested outcome:**", ticket["requested_outcome"] or "Unknown")

if "draft" not in st.session_state:
    st.session_state.draft = None
if "sources" not in st.session_state:
    st.session_state.sources = []
if "missing" not in st.session_state:
    st.session_state.missing = []
if "model_name" not in st.session_state:
    st.session_state.model_name = None
if "current_ticket_id" not in st.session_state:
    st.session_state.current_ticket_id = None

if st.session_state.current_ticket_id != ticket["id"]:
    st.session_state.draft = None
    st.session_state.sources = []
    st.session_state.missing = []
    st.session_state.model_name = None
    st.session_state.current_ticket_id = ticket["id"]

if st.button("Generate AI suggestion", type="primary"):
    with st.spinner("Retrieving current policy and drafting..."):
        query = f"{ticket['subject']} {ticket['message']} {ticket['requested_outcome'] or ''}"
        clauses = retrieve_current_clauses(query, top_k=4)

        # Outdated matching is only used to explain a possible trap.
        outdated = find_outdated_matches(query, top_k=1)

        if not clauses and outdated:
            st.session_state.draft = (
                "No applicable current policy clause was found for this ticket. "
                "A similar clause exists only in an outdated policy, so it has not "
                "been used as the basis for this response."
            )
            st.session_state.sources = []
            st.session_state.missing = []
            st.session_state.model_name = "policy-filter"
        else:
            draft, model_name = generate_draft(ticket, clauses)
            st.session_state.draft = draft
            st.session_state.sources = clauses
            st.session_state.missing = missing_information(ticket, clauses)
            st.session_state.model_name = model_name

if st.session_state.draft:
    st.divider()
    left, right = st.columns([1.15, 1])

    with left:
        st.subheader("Suggested reply")
        edited = st.text_area(
            "Agent-editable draft",
            value=st.session_state.draft,
            height=220,
            key=f"draft_editor_{ticket['id']}"
        )

        if st.session_state.missing:
            st.warning(
                "Missing information identified: "
                + ", ".join(st.session_state.missing)
            )

        st.caption(f"Model/mode: {st.session_state.model_name}")

    with right:
        st.subheader("Policy source")
        if st.session_state.sources:
            for source in st.session_state.sources:
                st.markdown(
                    f"**{source['document_name']} — {source['version']} — "
                    f"Clause {source['clause_number']}**"
                )
                st.caption(f"Similarity: {source['similarity']:.3f}")
                st.write(source["text"])
                st.divider()
        else:
            st.warning("No current policy clause was cited.")

    st.subheader("Human review")

    accept_locked = is_accept_locked(ticket["id"])

    if accept_locked:
        st.info(
            "This ticket has already been accepted. It cannot be accepted again "
            "unless the customer reopens it."
        )

        reopen_note = st.text_input(
            "Reason the customer reopened this ticket",
            key=f"reopen_note_{ticket['id']}",
            placeholder="Customer replied to the accepted reply",
        )

        if st.button("Reopen ticket"):
            if not reopen_note.strip():
                st.error("A reason is required to reopen the ticket.")
            else:
                record_reopen(ticket["id"], reopen_note.strip())
                st.success("Ticket reopened. Acceptance is available again.")
                st.rerun()

    approval_needed = st.checkbox(
        "Approval needed",
        help="Prototype assumption: the agent identifies whether a support-lead approval is needed."
    )

    c1, c2, c3 = st.columns(3)

    def log_webhook(message):
        print(message, flush=True)

        try:
            with open("webhook_debug.log", "a", encoding="utf-8") as handle:
                handle.write(f"{datetime.now().isoformat(timespec='seconds')} {message}\n")
        except OSError:
            pass


    def trigger_approval_workflow(ticket_id, decision, requested_outcome):
        webhook_url = os.getenv("MAKE_WEBHOOK_URL")
        log_webhook(f"trigger called: ticket={ticket_id} url_set={bool(webhook_url)}")

        if not webhook_url:
            return False, "MAKE_WEBHOOK_URL is not set, so no workflow was triggered."

        payload = {
            "ticket_id": ticket_id,
            "decision": decision,
            "requested_outcome": requested_outcome
        }

        try:
            response = requests.post(
                webhook_url,
                json=payload,
                timeout=10
            )

            log_webhook(f"response: {response.status_code} {response.text[:200]}")
            response.raise_for_status()
            return True, f"Approval workflow triggered successfully (HTTP {response.status_code})."

        except requests.RequestException as e:
            log_webhook(f"failed: {type(e).__name__} {e}")
            return False, f"Workflow trigger failed: {e}"


    def save_decision(decision, final_text, reason=None):
        conn = get_connection()
        now = datetime.now().isoformat()

        conn.execute(
            """INSERT INTO suggestions
            (ticket_id, draft, missing_information, model_name, created_at)
            VALUES (?, ?, ?, ?, ?)""",
            (
                ticket["id"],
                st.session_state.draft,
                ", ".join(st.session_state.missing),
                st.session_state.model_name or "unknown",
                now
            )
        )
        suggestion_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        for rank, source in enumerate(st.session_state.sources, start=1):
            conn.execute(
                """INSERT INTO suggestion_clauses
                (suggestion_id, clause_id, rank, similarity)
                VALUES (?, ?, ?, ?)""",
                (suggestion_id, source["clause_id"], rank, source["similarity"])
            )

        conn.execute(
            """INSERT INTO decisions
            (suggestion_id, decision, final_text, rejection_reason, approval_needed, created_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                suggestion_id,
                decision,
                final_text,
                reason,
                1 if approval_needed else 0,
                now
            )
        )
        decision_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        conn.close()
        return suggestion_id, decision_id


    def record_workflow_run(decision_id, status, detail):
        conn = get_connection()
        conn.execute(
            """INSERT INTO workflow_runs
            (decision_id, status, detail, simulated, created_at)
            VALUES (?, ?, ?, ?, ?)""",
            (
                decision_id,
                status,
                detail,
                0,
                datetime.now().isoformat()
            )
        )
        conn.commit()
        conn.close()


    with c1:
        if st.button("Accept draft", disabled=accept_locked):
            if is_accept_locked(ticket["id"]):
                st.error(
                    "This ticket was already accepted. Reopen it before accepting again."
                )
            else:
                sid, did = save_decision("accepted", edited)

                success, message = trigger_approval_workflow(
                    ticket_id=ticket["id"],
                    decision="accepted",
                    requested_outcome=ticket["requested_outcome"]
                )

                record_workflow_run(
                    did,
                    "triggered" if success else "failed",
                    message
                )

                st.success(
                    f"Accepted and saved. Decision ID created from suggestion {sid}."
                )

                if success:
                    st.success(message)
                else:
                    st.warning(message)

    with c2:
        if st.button("Save edited draft"):
            sid, _ = save_decision("edited", edited)
            st.success(f"Edited draft saved from suggestion {sid}.")

    with c3:
        if st.button("Reject draft"):
            reason = st.text_input("Rejection reason", key=f"reject_reason_{ticket['id']}")
            if not reason.strip():
                st.error("A rejection reason is required.")
            else:
                sid, _ = save_decision("rejected", edited, reason.strip())
                st.warning(f"Rejected and saved from suggestion {sid}.")

    st.divider()
    st.subheader("Simulated send")
    st.caption("This action changes nothing outside the prototype and sends no real message.")

    if st.button("Send reply (SIMULATED)"):
        st.success("SIMULATED ONLY — no customer message was sent.")

st.divider()
st.subheader("Audit history")

conn = get_connection()
history = conn.execute("""
    SELECT
        d.id AS decision_id,
        t.ticket_id,
        d.decision,
        d.approval_needed,
        d.rejection_reason,
        d.created_at,
        s.model_name,
        w.status AS workflow_status
    FROM decisions d
    JOIN suggestions s ON d.suggestion_id = s.id
    JOIN tickets t ON s.ticket_id = t.id
    LEFT JOIN workflow_runs w ON w.decision_id = d.id
    ORDER BY d.created_at DESC
""").fetchall()
conn.close()

if history:
    st.dataframe([dict(row) for row in history], width="stretch")
else:
    st.info("No decisions recorded yet.")

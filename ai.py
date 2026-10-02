import os
import requests

def missing_information(ticket, clauses):
    missing = []

    text = (ticket.get("message") or "").lower()
    if not ticket.get("order_ref"):
        missing.append("order reference")
    if "damage" in text and not any(
        word in text for word in ["photo", "photos", "picture", "pictures", "image"]
    ):
        missing.append("photos showing the damaged item and/or packaging")

    return missing

def deterministic_draft(ticket, clauses):
    if not clauses:
        return (
            "No applicable current policy clause was found for this ticket. "
            "The agent should review the request manually."
        )

    missing = missing_information(ticket, clauses)
    top = clauses[0]

    if missing:
        missing_text = ", ".join(missing)
        return (
            f"Thank you for contacting Jirani Home regarding your request. "
            f"Based on the current policy, we need the following information before "
            f"the request can be reviewed: {missing_text}. "
            f"We have not assumed any missing order details or confirmed an outcome."
        )

    if ticket["requested_outcome"] == "replacement":
        return (
            "Thank you for contacting Jirani Home. We have received your damaged-item "
            "request. Based on the current policy, the case can be reviewed for a "
            "replacement. The support team will review the reported damage and "
            "applicable requirements before confirming the outcome."
        )

    if ticket["requested_outcome"] == "return":
        return (
            "Thank you for contacting Jirani Home. We have received your return request. "
            "Based on the current policy, your request will be reviewed against the "
            "applicable return conditions before an outcome is confirmed."
        )

    if ticket["ticket_type"] == "warranty":
        return (
            "Thank you for contacting Jirani Home. We have received your warranty "
            "request. The product and reported fault will need to be reviewed against "
            "the applicable warranty conditions before eligibility is confirmed."
        )

    return (
        "Thank you for contacting Jirani Home. We have received your request. "
        "The support team will review it against the applicable current policy."
    )

def generate_draft(ticket, clauses):

    api_url = os.getenv("MODEL_API_URL")
    api_key = os.getenv("MODEL_API_KEY")
    model = os.getenv("MODEL_NAME", "prototype-model")

    if not api_url or not api_key:
        return deterministic_draft(ticket, clauses), "prototype-fallback"

    sources = "\n\n".join(
        f"[{c['document_name']} | {c['version']} | Clause {c['clause_number']}]\n{c['text']}"
        for c in clauses
    )

    prompt = f"""
You are a support drafting assistant.

Use ONLY the supplied policy clauses and ticket facts.
Never invent order numbers, dates, amounts, eligibility, refunds, approvals, or other facts.
Never make a refund, replacement, payment, or approval decision.
If required information is missing, state what is missing.
If no clause applies, say that no applicable current clause was found.

Ticket:
Subject: {ticket['subject']}
Type: {ticket['ticket_type']}
Message: {ticket['message']}
Order reference: {ticket.get('order_ref') or 'UNKNOWN'}
Delivery date: {ticket.get('delivery_date') or 'UNKNOWN'}
Requested outcome: {ticket.get('requested_outcome') or 'UNKNOWN'}

Current policy clauses supplied:
{sources}

Return only a professional draft reply for the support agent.
"""

    response = requests.post(
        api_url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0
        },
        timeout=20
    )
    response.raise_for_status()
    data = response.json()
    draft = data["choices"][0]["message"]["content"]
    return draft, model

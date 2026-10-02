# Jirani Home AI Policy Assistant — Prototype

This is a fictional prototype based on the Jirani Home case study.

IMPORTANT:
- The policy documents and tickets are fictional prototype data.
- They are not Jirani Home's real policies or customer records.
- The prototype does not send real customer messages or make refund/payment decisions.

## What this version implements

1. SQLite database
2. Current-policy filtering before retrieval
3. TF-IDF clause retrieval
4. Source display: document, version, clause
5. Ticket selection from seeded prototype tickets
6. AI suggestion interface with a deterministic fallback draft
7. Missing-information handling
8. Accept/edit/reject controls
9. Audit records, including webhook trigger status per decision
10. Make.com webhook trigger on acceptance (see [Make.com approval workflow](#makecom-approval-workflow))

## Run

```bash
uv venv env
source env/bin/activate
pip install -r requirements.txt
python setup_db.py
streamlit run app.py
```

The app opens in your browser.

## Demo runbook

1. Open the app and check the sidebar shows `Make.com webhook: configured`.
2. If you have already run the demo, tick **Clear decisions, drafts and reopen events** and press **Reset demo data** for a clean audit trail.
3. Open a ticket where a clause exists only in an outdated policy. The app refuses to cite it and explains that no current clause applies — this is the policy-versioning control.
4. Open a ticket with a matching current clause. Generate the suggestion, edit the text, and show the cited document, version and clause with its similarity score.
5. Tick **Approval needed**, then **Accept draft**. The decision is stored, the Make scenario fires, and the audit history shows the workflow status.
6. Click **Accept draft** again to show it is blocked. Reopen the ticket with a reason to show how the customer follow-up restores it.
7. Press **Send reply (SIMULATED)** to show that no real customer message is ever sent.

## Deploy

### Streamlit Community Cloud (free)

1. Put the project in a GitHub repository. Commit only these files:
   `app.py`, `ai.py`, `db.py`, `retrieval.py`, `setup_db.py`, `schema.sql`, `policies.json`, `development_tickets.json`, `requirements.txt`, `.streamlit/config.toml`.
   `.gitignore` already excludes `env/`, `jirani.db`, `.env` and `webhook_debug.log`.
2. Go to share.streamlit.io → **Deploy an app** → paste the repository URL and branch.
3. Set **Secrets** (Streamlit secrets, not a `.env` file):

```toml
MAKE_WEBHOOK_URL = "https://hook.eu1.make.com/<hook-id>"
MODEL_API_URL = "https://<your-endpoint>/v1/chat/completions"
MODEL_API_KEY = "<key>"
MODEL_NAME = "<model>"
```

Only `MAKE_WEBHOOK_URL` is required. Without `MODEL_API_URL` and `MODEL_API_KEY` the app uses the deterministic fallback draft.

4. Deploy. The database is not committed; `app.py` seeds `jirani.db` automatically on first start by calling `setup_db.py`.

Notes:
- The SQLite file lives on the server's filesystem. Each redeploy resets it, so audit history does not survive a redeploy. Move to a persistent database (PostgreSQL) if audit records must be kept.
- Anyone with the app URL can open tickets and trigger the Make scenario. This is a public demo host; do not put real customer data or real credentials in it.

### Docker (self-hosted)

```dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

```bash
docker build -t jirani-assistant .
docker run -p 8501:8501 --env-file .env jirani-assistant
```

Mount a volume at `/app` if you want `jirani.db` to persist between container restarts.

## Optional AI model

The prototype can use an OpenAI-compatible chat endpoint if these environment variables are supplied:

- MODEL_API_URL
- MODEL_API_KEY
- MODEL_NAME

If they are not supplied, the app uses a deterministic prototype draft. This lets the UI and retrieval workflow be demonstrated without an API key.

## Make.com approval workflow

Accepting a draft triggers a Make.com scenario over HTTP. The hook URL is read from an environment variable so it is never committed to source:

- MAKE_WEBHOOK_URL (for example `https://hook.eu1.make.com/<hook-id>`)

Put it in a `.env` file next to `app.py`:

```
MAKE_WEBHOOK_URL=https://hook.eu1.make.com/<hook-id>
```

`app.py` loads `.env` at startup. Values already present in the environment take precedence. `.env` is listed in `.gitignore`. The sidebar shows `Make.com webhook: configured` when the variable is set.

If it is not set, the draft is still accepted and saved, and the app reports that no workflow was triggered.

### Accept-once rule

A ticket can only be accepted once. After an accepted decision, **Accept draft** is disabled and the app explains why. Acceptance becomes available again only when the ticket is explicitly reopened, which is recorded in the `ticket_reopens` table with a reason and timestamp:

1. Open the accepted ticket.
2. Enter the reason the customer reopened it (required).
3. Click **Reopen ticket**. Acceptance is enabled again.

The lock is re-applied as soon as the reopened ticket is accepted a second time. The check runs again inside the accept handler, so a stale browser session cannot double-accept or fire a second webhook.

### Workflow

1. An agent generates a draft and edits it in the app.
2. The agent ticks **Approval needed** if a support lead must sign off.
3. Clicking **Accept draft** saves the suggestion, its cited clauses and the decision to the database.
4. The app then POSTs to `MAKE_WEBHOOK_URL` with a JSON body:

```json
{
  "ticket_id": 1,
  "decision": "accepted",
  "requested_outcome": "refund"
}
```

5. Make receives the request and runs the approval scenario (for example: route by requested outcome, notify the support lead in Slack, wait for approval, then hand off).

`decision` is always `accepted` from this button; `Save edited draft` and `Reject draft` record decisions locally without calling the webhook, because only acceptance starts the approval workflow.

### Make.com setup

1. Create a scenario whose first module is a **Custom webhook** and copy its URL into `MAKE_WEBHOOK_URL`.
2. Activate the scenario. A scenario left in draft still returns `200 Accepted` to the hook but never runs, which looks like a silent failure.
3. Use **Last received** in the webhook module to confirm the payload arrived.

### Troubleshooting

Every trigger attempt is logged to `webhook_debug.log` in the project directory and printed to the terminal running Streamlit:

```
2026-10-01T22:15:03 trigger called: ticket=1 url_set=True
2026-10-01T22:15:03 response: 200 Accepted
```

- No log file at all: the button has not been clicked since the logging was added, or the Streamlit process is running older code. Restart it with `streamlit run app.py`.
- `url_set=False`: `.env` is missing, or Streamlit was started from a different working directory.
- `response: 200 Accepted` but nothing happens in Make: the scenario is not activated.
- `failed: ...`: the machine running the app cannot reach `hook.eu1.make.com` (proxy or firewall).

Every attempt is also stored in the `workflow_runs` table and shown as **workflow_status** in the audit history at the bottom of the app, so the trigger outcome survives a restart.

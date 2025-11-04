# AI-Powered Trading Journal Agent

Intelligent backend services that capture multi-modal trading data, orchestrate asynchronous analyses, and surface actionable coaching insights to traders.

## Architecture Overview

- **Main Agent (FastAPI)** – Handles Google OAuth, receives raw multi-modal trade submissions, uses Gemini to extract structured fields, uploads media to Google Drive, and appends rows to the user's Google Sheet. Exposes REST endpoints under `/api`.
- **Analysis Sub-Agent (AWS Lambda)** – Triggered via SQS to perform long-running analysis with LangGraph. Pulls journal entries, downloads linked Drive assets, transcribes audio notes, analyzes chart images, optionally performs web research, and synthesizes reports (persisting insights back to DynamoDB).
  - Now leverages Google Gemini to generate multi-source coaching reports once journal data is retrieved.
- **Data & Messaging**
  - **Google Sheets / Drive** – User-owned storage for structured and unstructured trade artifacts.
  - **Amazon SQS** – Decouples synchronous ingestion from asynchronous analysis.
  - **Amazon DynamoDB** – Persists OAuth tokens and completed analysis reports.
  - **Amazon EventBridge** – Schedules proactive weekly analyses.

## Project Layout

```
app/                     FastAPI application source
  api/                   Route definitions
  clients/               Google & AWS client wrappers
  core/                  Config and logging helpers
  services/              Domain services (ingestion + queueing)
agents/analysis_lambda/  AWS Lambda analysis worker
infra/terraform/         Terraform IaC templates
```

## Local Development

1. **Install dependencies**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. **Environment variables**  
Set the following (e.g., via `.env`) to mirror the production configuration.

| Variable | Description |
| --- | --- |
| `APP_ENV` | Environment name (`development`, `staging`, `production`). |
| `APP_LOG_LEVEL` | Logging level (default `INFO`). |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` | OAuth 2.0 credentials. |
| `GOOGLE_DRIVE_ROOT_FOLDER_ID` | Optional Drive folder containing uploads. |
| `OAUTH_STATE_TTL` | Window (seconds) for OAuth state tokens to remain valid. |
| `OAUTH_SCOPES` | (Optional) Comma-separated overrides for Google OAuth scopes. |
| `TOKEN_ENCRYPTION_SECRET` | (Optional) 32+ char secret used to encrypt stored Google tokens (defaults to Google client secret). |
| `ANALYSIS_QUEUE_URL` | SQS queue endpoint (required for `/analysis/jobs`). |
| `DYNAMODB_TABLE_NAME` | DynamoDB table for tokens/reports. |
| `AWS_REGION` | AWS region for AWS clients. |
| `GEMINI_API_KEY` | Gemini access token. |
| `GEMINI_MODEL_NAME` / `GEMINI_VISION_MODEL_NAME` | Gemini model identifiers. |
| `SERPAPI_API_KEY` | (Optional) Enables web research enrichment via SerpAPI. |

3. **Run the API**

```bash
uvicorn app.main:app --reload --port 8000
```

4. **Run quality checks**

```bash
make lint
make test
```

5. **Key API routes**

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/health` | Basic health check. |
| `GET` | `/api/auth/google/authorize?user_id=...` | Returns Google OAuth authorization URL + state token bound to the user. |
| `POST` | `/api/auth/google/callback` | Exchanges the authorization code for tokens and stores them in DynamoDB. |
| `POST` | `/api/trades?sheet_id=...&sheet_range=Journal!A1` | Logs a trade with optional images/audio; appends to the specified sheet range. |
| `POST` | `/api/trades/submit?sheet_id=...` | Accepts raw text + attachments, uses Gemini to derive structured fields, then persists to Drive/Sheets. |
| `POST` | `/api/analysis/jobs` | Enqueues an analysis job (sheet id & prompt required; optional date range). |
| `GET` | `/api/analysis/jobs/{job_id}` | Retrieves job status/report from DynamoDB. |

> **Note:** Web research enrichment is optional and requires `SERPAPI_API_KEY`. When omitted, the analysis falls back to journal-derived insights only.
> Trade attachments are stored in the sheet as `drive_file_id|mime_type|shareable_link`, enabling the analysis worker to resolve metadata and retrieve binary content from Google Drive.

### Analysis Report Schema

Gemini responds with a deterministic JSON structure that downstream consumers can rely on. Each completed job stores the following payload in DynamoDB under the `report` attribute:

```json
{
  "performance_overview": {
    "summary": "...",
    "key_metrics": ["...", "..."]
  },
  "behavioural_patterns": ["..."],
  "opportunities": ["..."],
  "action_plan": [
    {
      "title": "...",
      "detail": "..."
    }
  ]
}
```

Related insights (`audio_insights`, `image_insights`, `external_research`) are persisted alongside the report for contextual drill-down. A Markdown rendering (`report_markdown`) is also stored to support quick display in dashboards.

## Analysis Lambda

- Entry point: `agents/analysis_lambda/handler.py`
- Bootstraps a LangGraph workflow that retrieves journal entries through the Google Sheets integration and stores results back in DynamoDB.
- Gemini now powers the text reasoning step, combining journal rows, voice-note sentiment, and chart insights into a Markdown coaching report.
- OAuth refresh/access tokens are encrypted before persisting to DynamoDB using a Fernet key derived from `TOKEN_ENCRYPTION_SECRET` (or the Google client secret when omitted).

### Google OAuth Flow

1. Call `GET /api/auth/google/authorize?user_id={userId}` to receive an `authorization_url` and signed `state` payload.
2. Redirect the trader to the Google consent screen; Google redirects back to your `GOOGLE_REDIRECT_URI` with `code` and the original `state`.
3. POST `{ "code": "...", "state": "..." }` to `/api/auth/google/callback` to exchange tokens and persist them in DynamoDB.
4. Once connected, trade ingestion and analysis endpoints automatically refresh access tokens when they are about to expire.

### Packaging

```bash
pip install -r requirements.txt --target build/
cp -R agents/analysis_lambda build/
cd build && zip -r ../analysis_lambda.zip .
```

Set Terraform variable `lambda_package_path` to `analysis_lambda.zip` before deploying.

## Infrastructure as Code

`infra/terraform` provisions:

- SQS queue for analysis jobs
- DynamoDB table for OAuth tokens and analysis reports
- IAM role/policies for the Lambda worker
- Lambda function & EventBridge schedule for proactive analyses
- CloudWatch log group and SQS trigger wiring

Example usage:

```bash
cd infra/terraform
terraform init
terraform plan -var='project_name=trading-journal' -var='lambda_package_path=../dist/analysis_lambda.zip'
terraform apply
```

Provide remaining variables (e.g., `gemini_api_key`) via CLI flags, a `.tfvars` file, or environment variables.

## Next Steps

- Encrypt stored Google refresh tokens and enforce rotation/TTL policies.
- Finish Gemini-based sentiment analysis, image inspection, and web research integrations.
- Extend the LangGraph workflow with audio transcription and image analysis steps.
- Backfill automated tests (FastAPI services, DynamoDB interactions) and add CI linters plus `terraform validate`.

## Operational Notes

- **Environment Integrity**
  - Run `make env-record ENV_FILE=/opt/pecunia/.env ENV_HASH=/opt/pecunia/.env.sha256` on a known-good deployment to capture the expected checksum once credentials are verified.
  - Install the automated drift detector with `sudo bash scripts/install_env_check_timer.sh` (copies `infra/systemd/pecunia-env-check.*` into `/etc/systemd/system` and enables a 5‑minute timer).
  - Alternatively, schedule `python -m scripts.check_env verify --env-file /opt/pecunia/.env --hash-file /opt/pecunia/.env.sha256` via cron if systemd timers are unavailable.
  - Before restarting services, run `scripts/pre_restart_check.sh /opt/pecunia/.env` or simply `make env-check ENV_FILE=/opt/pecunia/.env` to fail fast when required variables are missing.

- **API Quotas & Retries**
  - Google Drive downloads use built-in retries with exponential backoff (3 attempts). Monitor for `HttpError` spikes and consider service account whitelisting if volume grows.
  - SerpAPI calls retry automatically; track usage in the SerpAPI dashboard and adjust `num`/`engine` parameters for budget.
  - Gemini usage is subject to generative model quotas—ensure API key permissions cover audio+vision workloads.
- **Staging/Integration Testing**
  - Integration tests require valid Google OAuth credentials with Drive/Sheets scopes and a SerpAPI key. Configure these via GitHub Secrets and run a nightly workflow once manual verification is complete.
  - Current CI runs unit tests with stubs; e2e suites should mock external APIs or use dedicated sandbox accounts.

### Trade Submission Flow

1. The client calls `POST /api/trades/submit` with:
   - `content`: narrative text describing the trade.
   - `attachments`: optional list of base64-encoded files (images, audio, video) with filename & `mime_type`.
   - Optional explicit fields (`ticker`, `pnl`, etc.) to override Gemini output.
2. The main agent invokes Gemini to extract `ticker`, `pnl`, `position_type`, `entry_timestamp`, `exit_timestamp`, and `notes`.
3. Attachments are uploaded to Google Drive; the sheet row stores links in the format `drive_file_id|mime_type|shareable_link`.
4. Both JSON and Markdown summaries of the resulting analysis are available via DynamoDB (`report`, `report_markdown`).

**Attachment Limits:** Only `image/*`, `audio/*`, and `video/*` MIME types up to 15 MB per file are accepted. Files outside these bounds will be rejected with a `400` error.

If the client already has structured data, `POST /api/trades` remains available and bypasses Gemini.

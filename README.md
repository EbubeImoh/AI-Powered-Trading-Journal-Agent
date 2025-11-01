# AI-Powered Trading Journal Agent

Intelligent backend services that capture multi-modal trading data, orchestrate asynchronous analyses, and surface actionable coaching insights to traders.

## Architecture Overview

- **Main Agent (FastAPI)** – Handles Google OAuth, receives trade submissions, uploads media to Google Drive, and appends rows to the user's Google Sheet. Exposes REST endpoints under `/api`.
- **Analysis Sub-Agent (AWS Lambda)** – Triggered via SQS to perform long-running analysis with LangGraph. Pulls journal entries, transcribes audio, analyzes images, and synthesizes reports (Gemini integration planned).
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
| `ANALYSIS_QUEUE_URL` | SQS queue endpoint (required for `/analysis/jobs`). |
| `DYNAMODB_TABLE_NAME` | DynamoDB table for tokens/reports. |
| `AWS_REGION` | AWS region for AWS clients. |
| `GEMINI_API_KEY` | Gemini access token. |
| `GEMINI_MODEL_NAME` / `GEMINI_VISION_MODEL_NAME` | Gemini model identifiers. |

3. **Run the API**

```bash
uvicorn app.main:app --reload --port 8000
```

4. **Key API routes**

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/health` | Basic health check. |
| `GET` | `/api/auth/google/authorize` | Returns OAuth authorization URL + state token. |
| `POST` | `/api/trades?sheet_id=...` | Logs a trade with optional images/audio. |
| `POST` | `/api/analysis/jobs` | Enqueues an analysis job (sheet & prompt required). |
| `GET` | `/api/analysis/jobs/{job_id}` | Retrieves job status/report from DynamoDB. |

> **Note:** Google OAuth, Drive, Sheets, and Gemini integrations are stubbed with `NotImplementedError`. Replace these stubs with concrete API clients before production use.

## Analysis Lambda

- Entry point: `agents/analysis_lambda/handler.py`
- Bootstraps a LangGraph workflow that (eventually) loads journal data, performs multimodal analysis, and stores results back in DynamoDB.
- Current implementation produces a placeholder textual summary until Gemini and Google APIs are wired up.

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

- Implement Google OAuth token exchange + secure storage.
- Replace Google Drive/Sheets stubs with real API calls (likely via Google SDKs).
- Integrate Gemini text + vision models for high-quality analysis output.
- Build automated tests for core services and Terraform validations (e.g., `terraform validate`, `pytest`).

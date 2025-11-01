# AI-Powered Trading Journal Agent

<<<<<<< HEAD
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
=======
## Overview
The AI-Powered Trading Journal Agent is a backend-first platform that helps active traders capture and analyze every aspect of their trades. It combines a low-friction ingestion workflow with an asynchronous intelligence layer so users can journal quickly, retain ownership of their data, and receive personalized coaching that improves their trading discipline.

The system is organized around two cooperating agents:

* **Main Agent (FastAPI service):** Collects multi-modal trade inputs, persists them to the trader's Google assets, and provides an interactive API surface.
* **Analysis Sub-Agent (AWS Lambda worker):** Processes queued analysis jobs, runs deep pattern discovery with Gemini models, and produces actionable feedback stored for later retrieval.

## Core Problems Addressed
* **Tedious data entry:** Manual journaling is slow and inconsistent. The agent automates file uploads, structured logging, and note-taking so users can submit a full entry in seconds.
* **Scattered context:** Screenshots, audio reflections, and text notes live in different places. The agent correlates these artifacts inside Google Drive and Sheets and preserves relationships between them.
* **Lack of objective insight:** Traders rarely review their journals rigorously. The analysis sub-agent continuously mines the data to highlight recurring behaviors, sentiment trends, and execution mistakes, supplementing its findings with targeted web research.

## Feature Scope
### In-Scope Functionality
1. **Google OAuth 2.0 authentication**
   * Request Google Sheets and Google Drive scopes through the Main Agent.
   * Store encrypted refresh tokens (e.g., DynamoDB with KMS) so asynchronous jobs can operate on behalf of the user.
2. **Trade ingestion API (Main Agent)**
   * FastAPI endpoints accept trade metadata, images, and audio.
   * `upload_file_to_drive` uploads media to a user-owned Drive folder and returns shareable links.
   * `add_trade_to_sheet` writes a new row to the user's journal sheet, embedding Drive URLs and structured fields.
3. **Analysis pipeline (Sub-Agent)**
   * `queue_trade_analysis` enqueues analysis jobs into Amazon SQS.
   * An AWS Lambda function (built with LangGraph) pulls jobs, orchestrates tool calls, and compiles findings.
   * Tools include `read_trading_journal`, `transcribe_audio`, `analyze_trade_images`, and `google_web_search`.
   * Generated insights are written to DynamoDB so they can be surfaced asynchronously.
4. **Proactive reporting loop**
   * Amazon EventBridge triggers scheduled analyses (e.g., weekly retrospectives) without user intervention.
   * Notifications or summary reports can be pushed to email, chat, or exposed through future UI integrations.

### Out-of-Scope (Current Phase)
* Executing or automating live trades.
* Streaming or real-time market data ingestion.
* Dedicated frontend (web/mobile) experiences.

## Target Users
* **Active retail traders** seeking to institutionalize best practices and eliminate impulsive mistakes.
* **Prop-firm traders** who must maintain detailed journals for compliance and risk reviews.

## Architecture Overview
```
Trader → FastAPI Main Agent → (Sheets / Drive updates)
                        ↓
                 Amazon SQS queue → AWS Lambda Sub-Agent → (Gemini + analysis tools)
                        ↓
                    DynamoDB report store
```

### Main Agent Responsibilities
* Serve authenticated REST endpoints for trade submission and analysis requests.
* Manage OAuth 2.0 login flows, token refresh, and encryption of stored credentials.
* Orchestrate immediate actions: file uploads, sheet row creation, and job dispatch.

### Analysis Sub-Agent Responsibilities
* Consume SQS messages with user context and analysis prompts.
* Aggregate Google Sheet data, transcribe audio, and interpret images using Gemini Vision.
* Perform web research to contextualize detected patterns.
* Persist structured findings, sentiment scores, and recommendations for user retrieval.

## Technology Stack
| Layer | Technology | Purpose |
| --- | --- | --- |
| LLM | Google Gemini (Text + Vision) | Reasoning, pattern analysis, and content generation |
| Agent Orchestration | LangGraph | Deterministic state-machine style tool chaining |
| API Service | FastAPI on AWS (ECS Fargate or App Runner) | Hosts the Main Agent HTTP API |
| Async Processing | Amazon SQS + AWS Lambda | Decouple long-running analysis tasks |
| Data Stores | Google Sheets, Google Drive | Primary user-owned storage for journal entries |
| Secrets & Tokens | AWS DynamoDB (+ KMS) | Secure token persistence and report storage |
| Scheduling | Amazon EventBridge | Recurring triggers for proactive insights |
| Infrastructure as Code | Terraform / CloudFormation | Reproducible cloud environment setup |

## Data Lifecycle
1. User authenticates via Google OAuth and grants Drive/Sheets access.
2. Trader submits a journal entry through the FastAPI endpoint with text, attachments, and notes.
3. Files are uploaded to a structured Drive folder while metadata rows are inserted into the user's Google Sheet.
4. User or scheduler enqueues an analysis request.
5. The Lambda sub-agent collects relevant trade data, analyzes it with Gemini and supporting tools, and writes a report to DynamoDB.
6. Reports become accessible to the user via API or future notification channels.

## Local Development
1. **Clone the repository**
   ```bash
   git clone <repo-url>
   cd AI-Powered-Trading-Journal-Agent
   ```
2. **Create a virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
4. **Configure environment variables** (see below) and start the FastAPI server for development.
   ```bash
   uvicorn main:app --reload
   ```

## Environment Variables
| Variable | Description |
| --- | --- |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | OAuth credentials for the Google project. |
| `GOOGLE_REDIRECT_URI` | Callback URI configured in the Google console. |
| `DYNAMODB_TABLE_NAME` | DynamoDB table storing encrypted tokens and analysis reports. |
| `KMS_KEY_ID` | KMS key used to encrypt sensitive data before storage. |
| `SQS_QUEUE_URL` | URL of the Amazon SQS queue for analysis jobs. |
| `EVENTBRIDGE_BUS_NAME` | EventBridge bus used for scheduling recurring analyses. |
| `GEMINI_API_KEY` | Credential used to access Gemini APIs for analysis tasks. |

> Additional configuration such as AWS credentials, OAuth scopes, and Drive folder templates should be defined during infrastructure setup.

## Infrastructure Notes
* **Token security:** Store refresh tokens encrypted with AWS KMS before writing to DynamoDB.
* **Deployment packaging:** Bundle the Lambda sub-agent with dependencies (or leverage container images) and manage versions via IaC.
* **Observability:** Instrument both agents with CloudWatch metrics and structured logging to trace the analysis lifecycle.
* **Cost controls:** Configure SQS/Lambda concurrency limits and Drive/Sheets quotas to avoid unexpected usage spikes.

## Roadmap Highlights
1. Build FastAPI endpoints and Google OAuth integration.
2. Implement Drive/Sheets tooling and test end-to-end ingestion.
3. Stand up SQS and Lambda infrastructure, then connect `queue_trade_analysis`.
4. Integrate Gemini-based analysis with transcription and vision tooling.
5. Add proactive EventBridge triggers and notification pathways.
6. Explore user-facing interfaces (web dashboard, chat-based assistant) after backend stabilization.

## Contributing
1. Fork the repository and create a feature branch.
2. Adhere to repository linting and testing standards (TBD).
3. Submit a pull request detailing changes, tests, and validation steps.

## License
Specify the chosen license for the project (e.g., MIT, Apache 2.0) before release.

>>>>>>> eac423daf38678bd3397ef6c56c55133df8a01cf

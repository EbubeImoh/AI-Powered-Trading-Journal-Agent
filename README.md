# AI-Powered Trading Journal Agent

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


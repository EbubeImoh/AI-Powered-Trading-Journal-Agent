# Changelog

This document maintains a chronological record of project changes.

## [Unreleased]
- Added FastAPI application scaffolding with trade ingestion and analysis job endpoints.
- Introduced Google/AWS client wrappers and service layer stubs.
- Implemented Google OAuth callback handling, credential persistence, and Drive/Sheets integrations.
- Encrypted stored Google OAuth tokens using a Fernet-based cipher service shared by the API and analysis Lambda.
- Implemented analysis Lambda package with LangGraph workflow skeleton.
- Integrated Gemini-based report synthesis within the analysis Lambda for richer coaching output.
- Added Google Drive binary retrieval plus Gemini-powered audio transcription and chart analysis steps in the analysis workflow.
- Introduced optional SerpAPI web research integration feeding supplementary insights into analysis reports.
- Added pytest coverage for token encryption and credential refresh workflows.
- Added Makefile-based lint/test commands and unit tests covering multimodal analysis helpers.
- Standardised Gemini prompts to emit structured JSON reports and insight payloads for downstream consumers.
- Persisted Markdown-formatted report summaries alongside JSON for downstream presentation layers.
- Documented operational guidance around retries, quotas, and future integration testing strategy.
- Main agent now accepts raw multi-modal submissions, extracts structured trade fields via Gemini, and persists attachments to Drive/Sheets.
- Added attachment validation (MIME/size) and unit tests covering extraction, ingestion, and submission workflow stubs.
- Authored Terraform IaC templates for SQS, DynamoDB, Lambda, and EventBridge.
- Documented architecture and setup instructions in `README.md`.

## [2025-10-31] Initial repository setup
- Initialized Git repository with `main` branch.
- Added `.gitignore` to exclude Python artifacts and `.venv`.
- Created isolated Python virtual environment (`.venv`).
- Added baseline docs: `CHANGELOG.md`, `dev_scratchpad.md`, `requirements.txt`.
- Configured remote origin to `https://github.com/EbubeImoh/AI-Powered-Trading-Journal-Agent.git`.
- Committed and pushed initial content to `origin/main`.

Author: @EbubeImoh

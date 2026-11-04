# AlaiLink — Tamil Nadu Fisheries Scheme Assistant

[![CI](https://github.com/svaradhan981-commits/AlaiLink/actions/workflows/ci.yml/badge.svg)](https://github.com/svaradhan981-commits/AlaiLink/actions/workflows/ci.yml)
[![Live on Render](https://img.shields.io/badge/Render-Live%20Service-brightgreen)](https://alailink-rag.onrender.com)

- 🌐 **Live Deployment**: https://alailink-rag.onrender.com
- 🩺 **Health Check**: https://alailink-rag.onrender.com/health
- 📖 **API Docs (Swagger UI)**: https://alailink-rag.onrender.com/docs

## Problem

Fishing families in Tamil Nadu need information about ban-period relief, lean-period assistance, savings-cum-relief schemes, insurance, and boat registration. However, the rules and application procedures are scattered across government websites, policy documents, and e-Sevai service pages. Coastal villages often have weak internet connectivity, making heavy websites difficult to access. AlaiLink provides simple Tamil and English answers with official source citations and lightweight responses that work reliably even on slow networks.

## Who it is for

Secretary of a fishermen's cooperative society in Ramanathapuram who helps fishing families understand welfare schemes, check eligibility, and prepare applications.

## Signature feature

Low-bandwidth Tamil and English answers with official source citations and a 160-character summary that can be forwarded by SMS, even to members without smartphones.

## Hardest problem (my interview story)

The hardest problem is providing accurate, source-backed scheme information in simple Tamil while keeping responses lightweight enough for weak coastal internet connections. The system must identify the correct rules from multiple official documents, explain eligibility and required documents clearly, and avoid inventing or hallucinating scheme amounts or deadlines.

---

## Architecture

```
                    +-----------------------------+
                    |    Client / SMS Gateway     |
                    +--------------+--------------+
                                   |
                         HTTP / SSE Requests
                                   v
                    +-----------------------------+
                    |       FastAPI Server        |
                    | (CORS, Lifespan, Pydantic)  |
                    +--------------+--------------+
                                   |
            +----------------------+----------------------+
            |                                             |
            v                                             v
  +--------------------+                       +--------------------+
  |    Chat Service    |                       |   Usage Service    |
  |  (Retry / Timeout  |                       | (Cost Calculation) |
  | Fallback / Stream) |                       +---------+----------+
  +---------+----------+                                 |
            |                                            |
            v                                            v
+-----------------------+                    +-----------------------+
|  LLM Provider (Gemini |                    |  PostgreSQL/pgvector  |
|  OpenAI-Compatible)   |                    | (Usage Logs & Chunks) |
+-----------------------+                    +-----------------------+
```

---

## Technology Stack

- **Backend**: Python 3.12+, FastAPI, Uvicorn (ASGI)
- **Validation & Settings**: Pydantic v2, Pydantic-Settings
- **Database & Vectors**: PostgreSQL 16, pgvector extension, SQLAlchemy 2.0 (AsyncIO), Psycopg 3
- **HTTP & Resilience**: HTTPX (async client with retries, timeouts, fallback, SSE streaming)
- **Containerization**: Docker, Docker Compose
- **CI/CD**: GitHub Actions
- **Cloud Hosting Target**: Render (Web Service + Managed PostgreSQL)
- **Testing & Quality**: Pytest, AnyIO, Ruff

---

## Folder Structure

```
AlaiLink/
├── .github/
│   └── workflows/
│       └── ci.yml               # GitHub Actions CI pipeline
├── app/
│   ├── services/
│   │   ├── __init__.py
│   │   ├── chat.py              # LLM integration, retry, timeout, fallback, streaming
│   │   ├── documents.py         # Document parsing and chunking
│   │   ├── embeddings.py        # Text vector embedding adapters
│   │   ├── rag.py               # Vector similarity context retrieval
│   │   └── usage.py             # LLM usage logging and cost analytics
│   ├── __init__.py
│   ├── config.py                # Environment and application configuration
│   ├── database.py              # SQLAlchemy async engine, vector and usage models
│   ├── ingest.py                # Document ingestion pipeline
│   ├── main.py                  # FastAPI application and route declarations
│   └── schemas.py               # Pydantic request and response schemas
├── data/
│   ├── raw/                     # Raw official PDFs and crawled pages (local)
│   └── sample/                  # Committed representative data samples
├── docker/
│   └── init.sql                 # Database initialization script (pgvector)
├── docs/
│   ├── DATASET.md               # Dataset inventory and source URLs
│   └── QUESTIONS.md             # 10 real-world evaluation questions
├── tests/
│   ├── conftest.py              # Pytest fixtures and test client
│   ├── test_chat.py             # Chat, streaming, retry, timeout, fallback tests
│   ├── test_documents.py        # Text parsing and chunking tests
│   ├── test_embeddings.py       # Embedding adapter tests
│   ├── test_health.py           # /health and /hello endpoint tests
│   ├── test_rag.py              # Evidence retrieval and formatting tests
│   └── test_usage.py            # Usage recording and cost calculation tests
├── tools/
│   └── download.py              # Web crawler and PDF download utility
├── .dockerignore                # Docker build context exclusion rules
├── .env.example                 # Environment variable template
├── .gitignore                   # Git exclusion rules
├── Dockerfile                   # Production container definition
├── docker-compose.yml           # Multi-container orchestration (API + PostgreSQL)
├── PROGRESS.md                  # Milestone progress tracking
├── pyproject.toml               # Ruff and Pytest configuration
├── README.md                    # Project documentation
├── requirements.txt             # Production dependencies
├── requirements-dev.txt         # Development and testing dependencies
└── urls.txt                     # Seed URLs for official data collection
```

---

## Dataset

| Source | Link | Documents | Pages / Format | Licence / Terms |
|---|---|---:|---:|---|
| Tamil Nadu Fisheries Department | https://www.fisheries.tn.gov.in/ | 48 pages | HTML/Text | Official Government Portal |
| Department Notifications & Orders | https://www.fisheries.tn.gov.in/ | 11 PDFs | PDF | Official Departmental Circulars |
| RTI Acts and Rules | https://www.fisheries.tn.gov.in/ | 4 PDFs | PDF | Public Right to Information |

- Detailed inventory: [docs/DATASET.md](docs/DATASET.md)
- Committed data sample: `data/sample/`
- Evaluation queries: [docs/QUESTIONS.md](docs/QUESTIONS.md)

---

## 10 Real Questions

1. மீன்பிடி தடை கால நிவாரணம் எவ்வளவு? எப்போது கிடைக்கும்?
2. What documents are needed for ban-period relief at the e-Sevai centre?
3. How much must a fisherwoman save to get the savings-cum-relief amount?
4. Who is eligible for ban-period relief?
5. How can I apply for the savings-cum-relief scheme?
6. What documents are required for boat registration?
7. How can I update my boat registration details?
8. What insurance schemes are available for fishing families?
9. Where can I contact the Fisheries Department for application assistance?
10. Can I get an immediate loan subsidy for purchasing deep-sea trawlers without cooperative society membership? *(Unverified query)*

See [docs/QUESTIONS.md](docs/QUESTIONS.md) for document mappings.

---

## Local Installation and Setup

### 1. Prerequisites
- Python 3.12 or higher
- Git

### 2. Setup Virtual Environment
```bash
# Clone the repository
git clone https://github.com/svaradhan981-commits/AlaiLink.git
cd AlaiLink

# Create and activate virtual environment
python -m venv .venv
# On Windows PowerShell:
.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements-dev.txt
```

### 3. Configure Environment Variables
```bash
# Copy example configuration
cp .env.example .env   # On Windows: copy .env.example .env
```
Edit `.env` to configure your API keys and database connection:
```ini
APP_NAME=AlaiLink
ENVIRONMENT=local
ALLOWED_ORIGINS=*

# LLM Configuration (OpenAI-compatible Gemini endpoint)
LLM_PROVIDER=openai_compatible
LLM_MODEL=gemini-3.5-flash-lite
LLM_FALLBACK_MODEL=gemini-1.5-flash
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
LLM_API_KEY=your_gemini_api_key_here

# Reliability Settings
LLM_TIMEOUT_SECONDS=90
LLM_MAX_RETRIES=1
LLM_RETRY_DELAY_SECONDS=1

# Pricing (USD per 1,000,000 tokens)
LLM_DEFAULT_INPUT_COST_PER_MILLION=0.075
LLM_DEFAULT_OUTPUT_COST_PER_MILLION=0.30

# PostgreSQL Connection
DATABASE_URL=postgresql+psycopg://alailink:alailink@localhost:5432/alailink
```

### 4. Run Locally
```bash
uvicorn app.main:app --reload --port 8000
```

---

## API Endpoints

### 1. Health and Liveness Checks
- `GET /health`: Fast liveness check that does not call the database or LLM.
  ```bash
  curl http://localhost:8000/health
  # Response: {"status":"ok","app":"AlaiLink","environment":"local"}
  ```
- `GET /hello`: Basic greeting endpoint.
  ```bash
  curl http://localhost:8000/hello
  # Response: {"message":"Hello  AlaiLink in local!"}
  ```

### 2. Synchronous Chat (`POST /chat`)
Sends a query in Tamil or English and receives a structured JSON response.

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"மீன்பிடி தடை கால நிவாரணம் எவ்வளவு?","language":"ta"}'
```

**Response Format**:
```json
{
  "answer": "மீன்பிடி தடைக்கால நிவாரணத் தொகையாக ₹5,000/- வழங்கப்படுகிறது. [1]",
  "language": "ta",
  "sources": [
    {
      "title": "Relief Assistance during Fishing Ban period",
      "url": "https://www.fisheries.tn.gov.in/pages/view/Relief_Assistance_during_Fishing_Ban_period"
    }
  ],
  "summary": "மீன்பிடி தடைக்கால நிவாரணத் தொகை ₹5,000/- வழங்கப்படும்."
}
```

*Policy*: If no relevant verified evidence is retrieved, AlaiLink returns a clear unable-to-verify response rather than hallucinating scheme rules.

### 3. Progressive Streaming (`POST /chat/stream`)
Uses Server-Sent Events (SSE) for low-latency token streaming.

```bash
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"question":"Who is eligible for ban-period relief?","language":"en"}'
```

**Stream Events**:
- `event: delta`: Progressive JSON chunks.
- `event: reset`: Discards partial state if a retry occurs before success.
- `event: complete`: Final validated `ChatResponse` payload.
- `event: error`: Safe error details if provider failure persists.

### 4. Usage and Cost Analytics (`GET /usage`)
Returns persistent request records, token aggregates, and estimated costs from PostgreSQL.

```bash
curl http://localhost:8000/usage
```

**Response Format**:
```json
{
  "total_requests": 14,
  "successful_requests": 12,
  "failed_requests": 2,
  "total_prompt_tokens": 8450,
  "total_completion_tokens": 1820,
  "total_tokens": 10270,
  "total_cost": 0.00117975,
  "by_model": {
    "gemini-3.5-flash-lite": {
      "requests": 12,
      "successful_requests": 11,
      "failed_requests": 1,
      "prompt_tokens": 7650,
      "completion_tokens": 1620,
      "total_tokens": 9270,
      "cost": 0.00105975
    },
    "gemini-1.5-flash": {
      "requests": 2,
      "successful_requests": 1,
      "failed_requests": 1,
      "prompt_tokens": 800,
      "completion_tokens": 200,
      "total_tokens": 1000,
      "cost": 0.00012000
    }
  },
  "recent_records": [...]
}
```

---

## Reliability Features

- **Timeouts**: Handled with `asyncio.timeout` and `httpx.Timeout`. Returns HTTP 504 on timeout.
- **Retries**: Configurable exponential backoff retrying transient failures (HTTP 429, 5xx, network drops).
- **Fallback Model**: Automatically routes requests to `LLM_FALLBACK_MODEL` if the primary model fails after retries due to eligible transient errors. Permanent client errors (400, 401, 403, 422) fail immediately without fallback or retries.
- **Safe Cost Tracking**: If provider token metadata is omitted, values are recorded as `None` without guessing zero or fabricating costs. Secrets and API keys are never stored in logs or database records.

---

## Docker Compose Setup

Run the full stack (FastAPI Application + PostgreSQL 16 with pgvector) locally:

```bash
# Start all services in the background
docker compose up --build -d

# Check service logs
docker compose logs -f

# Verify service health
curl http://localhost:8000/health
curl http://localhost:8000/usage

# Shut down and preserve volume data
docker compose down

# Shut down and wipe database volume
docker compose down -v
```

---

## Automated Testing and CI

### Run Tests Locally
```bash
# Run full test suite
pytest -v

# Run code style & lint checks
ruff check .

# Check application import
python -c "import app.main; print('Application imported successfully.')"
```

### GitHub Actions CI
The CI workflow defined in [`.github/workflows/ci.yml`](.github/workflows/ci.yml) triggers on every push and pull request to `main`. It:
1. Sets up Python 3.12 with pip cache.
2. Installs dependencies from `requirements-dev.txt`.
3. Validates code quality using `ruff check .`.
4. Tests import integrity.
5. Runs the full automated test suite with `pytest -v`.

---

## Deployment to Render

AlaiLink is pre-configured for deployment on Render as a Web Service:

### 1. Provision PostgreSQL with pgvector
1. In Render Dashboard, click **New +** -> **PostgreSQL**.
2. Name the database `alailink-db`.
3. Copy the **Internal Database URL**.
4. In the database query tool, run:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

### 2. Deploy Web Service
1. Click **New +** -> **Web Service** -> Connect your GitHub repository `AlaiLink`.
2. Configure settings:
   - **Environment**: `Docker`
   - **Dockerfile Path**: `Dockerfile`
   - **Docker Context**: `.`
   - **Instance Type**: Free or Starter
3. Add Environment Variables under **Environment**:
   - `ENVIRONMENT`: `production`
   - `PORT`: `8000` (Render injects its own port dynamically; the Dockerfile handles `${PORT:-8000}`)
   - `ALLOWED_ORIGINS`: `*` (or your frontend domain)
   - `DATABASE_URL`: Your Render PostgreSQL connection string
   - `LLM_PROVIDER`: `openai_compatible`
   - `LLM_MODEL`: `gemini-3.5-flash-lite`
   - `LLM_FALLBACK_MODEL`: `gemini-1.5-flash`
   - `LLM_BASE_URL`: `https://generativelanguage.googleapis.com/v1beta/openai/`
   - `LLM_API_KEY`: *(Set secret Gemini API key in Render secret manager)*
4. Health Check Path: `/health`.
5. Deploy the service.

### 3. Deployed Service Endpoints
- **Live Base URL**: `https://alailink-rag.onrender.com`
- **Health Check**: `https://alailink-rag.onrender.com/health`
- **Interactive Documentation**: `https://alailink-rag.onrender.com/docs`
- **Usage & Cost Analytics**: `https://alailink-rag.onrender.com/usage`

---

## Known Limitations

1. **Scanned PDF OCR**: Currently, the parser extracts text directly from digitally generated PDFs and HTML pages. Scanned image-only PDFs without an embedded text layer require external OCR, which is not included in the standard lightweight footprint.
2. **Evidence Dependency**: When official documents are not present in the vector store or return no relevant matches, the system refuses to speculate and returns an explicit unverified message to maintain safety for government scheme applicants.
# AlaiLink — Tamil Nadu Fisheries Scheme Assistant

## Problem

Fishing families in Tamil Nadu need information about ban-period relief, lean-period assistance, savings-cum-relief schemes, insurance, and boat registration. However, the rules and application procedures are scattered across government websites, policy documents, and e-Sevai service pages. Coastal villages often have weak internet connectivity, making heavy websites difficult to access. AlaiLink provides simple Tamil answers with official source citations and lightweight responses that work even on slow networks.

## Who it is for

Secretary of a fishermen's cooperative society in Ramanathapuram who helps fishing families understand welfare schemes, check eligibility, and prepare applications.

## Signature feature

Low-bandwidth Tamil answers with source citations and a 160-character Tamil summary that can be forwarded by SMS, even to members without smartphones.

## Hardest problem (my interview story)

The hardest problem is providing accurate, source-backed scheme information in simple Tamil while keeping responses lightweight enough for weak coastal internet connections. The system must identify the correct rules from multiple official documents, explain eligibility and required documents clearly, and prepare application packs with human approval from the cooperative society secretary.

## Dataset

| Source | Link | Documents | Pages | Licence / terms |
|---|---|---:|---:|---|
| Tamil Nadu Fisheries and Fishermen Welfare Department | https://www.fisheries.tn.gov.in/ | To be counted | To be counted | Verify official website and document reuse terms |
| Tamil Nadu Government policy notes (2021–2026) | https://www.tn.gov.in/ | To be counted | To be counted | Verify terms for each document |
| Tamil Nadu e-Sevai service pages | https://www.tnesevai.tn.gov.in/ | To be counted | To be counted | Verify website and service-specific terms |

**Dataset target:** 700+ pages covering fisheries welfare schemes, ban-period relief, savings-cum-relief, insurance, boat registration, department booklets, policy notes, and relevant e-Sevai services.

## 10 real questions

1. மீன்பிடி தடை கால நிவாரணம் எவ்வளவு? எப்போது கிடைக்கும்?
2. What documents are needed for ban-period relief at the e-Sevai centre?
3. How much must a fisherwoman save to get the savings-cum-relief amount?
4. Who is eligible for ban-period relief?
5. How can I apply for the savings-cum-relief scheme?
6. What documents are required for boat registration?
7. How can I update my boat registration details?
8. What insurance schemes are available for fishing families?
9. Where can I contact the Fisheries Department for application assistance?
10. How can I check the eligibility requirements for a fisheries welfare scheme?

See [docs/QUESTIONS.md](docs/QUESTIONS.md).

## Run it

```bash
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                # Windows: copy .env.example .env
uvicorn app.main:app --reload
curl http://localhost:8000/health
```

## Chat and retrieval API

Configure `LLM_API_KEY` in your local `.env` file. The initial client uses an
OpenAI-compatible chat-completions endpoint; configure `LLM_MODEL`, `LLM_BASE_URL`,
and `LLM_TIMEOUT_SECONDS` there as needed. API keys are never stored in source.

```bash
curl -X POST http://localhost:8000/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"question\":\"மீன்பிடி தடை கால நிவாரணம் எவ்வளவு?\",\"language\":\"ta\"}"
```

The endpoint returns a structured answer, language, sources, and a summary capped
at 160 characters. It retrieves chunks from PostgreSQL/pgvector and asks the model
to answer only from those cited official documents. If no relevant, URL-backed
evidence is found, the API returns a clear unable-to-verify answer without asking
the LLM to guess. A missing API key returns HTTP 503, a provider timeout returns
HTTP 504, and other provider failures return HTTP 502.

For progressive Server-Sent Events, use `POST /chat/stream` with the same JSON
request. `delta` events contain JSON-output fragments from the provider, `reset`
indicates that a failed partial attempt was discarded before a retry/fallback,
`complete` contains the validated chat response, and `error` contains a safe error
message. In Swagger, open `/docs`, choose `POST /chat/stream`, and execute a request;
for streaming event inspection, use an SSE-capable client such as `curl -N`.

## Document retrieval

Set `DATABASE_URL` and the embedding variables shown in `.env.example`. The default
embedding adapter uses Gemini's `gemini-embedding-001` model with 768 dimensions;
it uses `EMBEDDING_API_KEY` when set and otherwise reuses `LLM_API_KEY`. Vector
dimensions are checked before storage and retrieval. `EMBEDDING_PROVIDER=openai_compatible`
can be used with a compatible embeddings endpoint. Adjust `RAG_MAX_DISTANCE` only
after evaluation.

Run the repeatable ingestion command after PostgreSQL with pgvector is available:

```powershell
python -m app.ingest
```

It reads text pages from `data/raw/pages/`, PDFs from `data/raw/pdfs/` and PDF
files at `data/raw/`, extracts text, chunks on sentence boundaries where possible,
and inserts only chunks not already present for the selected embedding model and
dimension. Scanned PDFs without an extractable text layer are skipped with a log
message; image OCR is not included.

## Live link

Coming in Week 2.
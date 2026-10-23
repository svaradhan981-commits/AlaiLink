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

## Live link

Coming in Week 2.
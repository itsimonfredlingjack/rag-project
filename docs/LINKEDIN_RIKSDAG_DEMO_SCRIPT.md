# LinkedIn Demo Script: Svensk Ragg Public Riksdagen Demo

Target length: 75-90 seconds.

## Opening

"I built a small local Swedish RAG demo over Riksdagens öppna data.

This is not legal advice, and it is not all Swedish law or my full private lab
corpus. The public demo is deliberately Riksdagen-only."

## Shot 1: Readiness

Show `/api/svensk-ragg/ready`.

"First I check readiness. The public profile is
`degraded_but_usable`, with `can_answer=true`.

That degraded state is expected here: Chroma is disabled, and the public demo
uses BM25 only over the Riksdagen public corpus."

On screen:

```json
"status": "degraded_but_usable"
"can_answer": true
"profile": "public-riksdag-demo"
"corpus_scope": "riksdagen_open_data_only"
```

## Shot 2: Grounded Answer

Ask:

```text
Offentlighetsprincipen
```

"Now I ask a bounded public question. The answer is generated locally and shows
source IDs from Sveriges riksdag / Riksdagens öppna data."

Point to:

- `Käll-ID`
- answer latency
- data-source attribution
- source IDs such as `GP02K1`, `GMB132`, `H2B191`

## Shot 3: Source Inspector

Open `Visa hämtade källor`.

"The important part is the source inspector. I can inspect each retrieved chunk:
`document_id`, `source_scope`, `retriever_source`, and the Riksdagen URL.

For the public demo, the source scope should stay
`riksdagen_open_data_only`."

## Shot 4: Refusal

Ask:

```text
Har jag rätt att stämma min arbetsgivare om detta?
```

"The demo should not give personalized legal advice. Here it refuses and exposes
`refusal_reason=legal_advice`."

Point to:

- refusal styling
- `refusal_reason`
- no retrieved private sources

## Eval Evidence

"I also added a 30-question public smoke/eval run. In this current run:
retrieval_hit@5 was 0.900, citation_present_rate was 1.000,
refusal_correctness was 1.000, and critical_failure_count was 0.

Those are eval-run numbers, not product guarantees."

## Close

"The goal is not to claim a universal legal assistant. The goal is a bounded,
inspectable local RAG demo: named public data source, clear refusal behavior,
visible sources, and repeatable eval evidence."

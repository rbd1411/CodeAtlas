# How to present CodeAtlas

## One sentence

CodeAtlas is a local-first code RAG system that combines structure-aware indexing and hybrid retrieval to answer repository questions with verifiable file-and-line evidence.

## 30-second pitch

Developers joining an unfamiliar codebase spend a lot of time searching for where behavior is implemented. CodeAtlas indexes functions, classes, methods, documentation, and source metadata instead of using arbitrary chunks. It retrieves with both embeddings and BM25, then produces an answer grounded in numbered source blocks. The differentiator is not merely chatting with code—it is traceable evidence, safe local operation, and a retrieval design suited to exact identifiers as well as conceptual questions.

## Two-minute walkthrough

1. Add a local folder or public GitHub repository.
2. The scanner applies safety and ignore rules and detects supported text languages.
3. Python uses AST boundaries; several other languages use declaration-aware parsing; Markdown uses headings.
4. Every chunk retains its path, symbol, kind, and exact lines.
5. A local or OpenAI embedding is persisted with the chunk in SQLite.
6. A question is ranked by cosine similarity, BM25, and file/symbol matching.
7. Results are diversified across files so one large file does not dominate.
8. Local mode extracts evidence; OpenAI mode synthesizes it under a strict evidence-only prompt.
9. The UI makes every citation inspectable.

## Whiteboard version

Draw five boxes:

```text
Repository → Structural chunks → Hybrid index → Grounded generator → Cited UI
```

Under **Structural chunks**, write `path + symbol + lines`. Under **Hybrid index**, write `vector + BM25 + metadata`. Under **Grounded generator**, write `evidence only / abstain`. This communicates the essential design in under a minute.

## Common questions and strong answers

### Is this just “chat with a repository”?

The chat surface is secondary. The engineering work is in structure-aware ingestion, hybrid ranking, source provenance, safe repository access, provider abstraction, and honest abstention. The answer is useful because every claim can be traced to an indexed snapshot.

### Why not use only vector search?

Code contains exact identifiers, paths, error strings, and API names. BM25 is often better for those. Vector similarity helps when the question and code use different conceptual wording. Hybrid fusion covers both patterns.

### Why not send the whole repository to the model?

Repositories exceed practical context limits, cost more, expose more private code, and introduce distracting evidence. Retrieval narrows the prompt to the small set of sources most likely to answer the question.

### How do citations stay accurate?

Line ranges are captured while reading the indexed file and stored with each chunk. The API returns citations from those stored records rather than asking the model to invent them. The model only emits citation numbers mapped to retrieved records.

### What prevents hallucination?

No system eliminates it completely. CodeAtlas reduces it by restricting generation to retrieved evidence, requiring citations, explicitly permitting “insufficient evidence,” treating repository text as untrusted, showing the evidence to the user, and reporting a retrieval-based confidence label.

### What happens without an API key?

Feature hashing produces deterministic local vectors, BM25 supplies lexical ranking, and extractive mode returns the strongest matching source lines. That proves the full indexing, retrieval, and citation pipeline while keeping the demo private and reproducible.

### What would you change for production?

I would add identity and repository authorization, isolate ingestion workers, run secret scanning, use incremental indexing, move vectors to pgvector or a managed vector service, add a reranker and graph expansion, stream progress, and continuously measure retrieval recall and citation faithfulness.

### Why store full file content in SQLite?

It makes citations and file previews independent of later filesystem changes and creates a consistent indexed snapshot. The trade-off is duplicated source data and the need for encryption/retention controls in a shared service.

### Why is confidence not a probability?

It is derived from retrieval score strength and supporting-result count. A calibrated correctness probability would require labeled evaluation data and calibration. The interface therefore calls it a confidence heuristic and still encourages verification.

### How does CodeAtlas handle prompt injection in source files?

The answer prompt labels repository blocks as untrusted evidence and tells the model never to follow instructions found there. The generator has no tools, so repository text cannot trigger actions. Production should retain this control and add model/red-team evaluation.

## Demo script

Use the bundled TinyShop project and ask these in order:

1. `Explain the architecture of this repository.`
2. `How is token expiration validated and handled?`
3. `Trace order creation from the route to the event.`
4. `Which test covers expired tokens?`
5. `Does the repository show how refresh tokens are validated?`

The final question demonstrates abstention behavior because the demo contains no refresh-token implementation.

## Terms to use accurately

- Say **structure-aware** for the current multi-language chunking. Do not claim full AST parsing outside Python.
- Say **hybrid retrieval**, not “vector database”; vectors currently live in SQLite JSON.
- Say **local feature-hashing embeddings**, not a local neural model.
- Say **import edges are stored for future graph retrieval**; they are not yet part of scoring.
- Say **retrieval-based confidence heuristic**, not calibrated certainty.
- Say **portfolio-complete/local-first**, not internet-ready multi-tenant production SaaS.

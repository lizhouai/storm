# Examples

These checked-in examples show the two public workflows provided by the `storm` skill. They are proof of output shape and source traceability, not benchmark results.

## Classic STORM artifact bundle

[RAG evaluation frameworks](classic-rag-evaluation/README.md) starts from one research prompt and preserves the complete four-file contract:

- topic-only direct outline
- evidence-refined outline
- cited draft article
- polished article with references and verification notes

## Prompt-native Co-STORM preview

[RAG evaluation roundtable](co-storm-rag-evaluation/README.md) shows a compact interactive run with visibly attributed simulated participants, a moderator handoff, a cited mind-map delta, and choice-first steering.

[RAG technology research](co-storm-rag-technology/README.md) follows a complete
interactive run from warm start through four user-steered research rounds,
explicit file-producing work, and the final `生成报告` instruction. Its
[rendered HTML report](https://lizhouai.github.io/storm-research-skill/examples/co-storm-rag-technology/rag-technology-research-report.html)
is checked in as the end-to-end output snapshot.

## Provenance

- Compact examples generated: 2026-07-10
- End-to-end Co-STORM report generated: 2026-07-11
- Source boundary: research papers and official technical documentation linked from each example
- Retrieval dates: 2026-07-10 and 2026-07-11 respectively
- Validation: citation targets and artifact structure were checked; no experimental results were independently reproduced

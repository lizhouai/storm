# Prompt-native Co-STORM example: RAG technology research

This end-to-end snapshot was produced by the current prompt-native Co-STORM
preview on 2026-07-11. It shows how one warm start can continue through a
user-steered sequence and then close with a final file artifact. The visible
participants are simulated research roles, not independently running agents or
the upstream `CoStormRunner`.

## Final report

- [Open the rendered HTML report](https://lizhouai.github.io/storm-research-skill/examples/co-storm-rag-technology/rag-technology-research-report.html)
- [View the checked-in HTML source](rag-technology-research-report.html)

The report covers production RAG architecture, Chunking, Hybrid Retrieval,
Reranker design, advanced RAG boundaries, evaluation, security, and an
implementation roadmap. It cites 20 papers or official technical sources.

## Starting prompt

```text
Use the storm skill in Co-STORM mode to research RAG technology.
```

## Steering path

The run did not use a fixed number of rounds. Each numeric reply selected one
of the visible choices offered by the Moderator.

| Stage | User input | Selected branch |
|---|---|---|
| Warm start | Initial prompt | RAG foundations, retrieval architectures, production evaluation, and the initial mind map |
| Round 2 | `1` | Production-grade RAG architecture |
| Round 3 | `2` | Chunking, Hybrid Retrieval, and Reranker |
| Round 4 | `1` | Golden test sets and launch metrics |
| Round 5 | `1` | Executable evaluation contracts |
| File-producing turn | `1` | Persist the evaluation kit and validate it |
| Conclusion | `生成报告` | Synthesize the selected branches into the final HTML report |

## Final-report trigger

The concluding user message was deliberately short:

```text
生成报告
```

The preceding turn had already explicitly authorized persistent file output,
so the instruction closed the roundtable and produced the HTML report. In a
fresh conversation, make the file intent explicit, for example:

```text
Conclude the Co-STORM roundtable and save the final report as HTML.
```

Without file authorization, the conversation-first mode should return the
report in chat instead of writing it to disk.

## Validation snapshot

- The report is static, self-contained HTML with no scripts.
- Its internal anchors and 52 links were checked.
- External links use HTTPS.
- A browser rendering pass checked Chinese text, navigation, cards, citations,
  dark mode, and narrow-screen layout.
- This is an output-shape example, not a benchmark or independent reproduction
  of the cited results.

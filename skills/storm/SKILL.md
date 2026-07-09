---
name: storm
version: 0.3.0
description: Use when Codex needs STORM-style deep research, technical or literature surveys, background reviews, cited reports, source-grounded synthesis, standard STORM artifact files, local STORM runner execution, or interactive Co-STORM exploration. Use for research, 调研, surveys, source comparison, cited articles, and mind-map or roundtable exploration.
---

# STORM Research

## Overview

Use the Stanford STORM pattern for source-grounded research: generate diverse writer perspectives, run search-backed simulated interviews, create a direct outline, refine the outline from gathered evidence, write section by section with inline citations, polish the article, then verify citation support and evidence gaps.

Default to file-producing Artifact STORM for non-interactive research. If the user does not specify an output format, write the standard STORM artifacts as HTML files. Do not substitute an in-chat brief for the artifact files unless the user explicitly asks for "chat only", "no files", or a quick answer.

For detailed prompts, schemas, and quality gates, read `references/storm-method.md`.

## Mode Selection

| User intent | Use | Deliverable |
|---|---|---|
| "research", "survey", "调研一下", "技术调研", "background review" | Artifact STORM | Four standard files: `direct_gen_outline`, `storm_gen_outline`, `storm_gen_article`, `storm_gen_article_polished`; default format `.html` |
| "write a full article", "Wikipedia-style", "完整长文", "save files" | Artifact STORM | Same four standard files, with article depth adjusted to the request |
| "run STORM", "use this repo/script/venv", "local STORM pipeline" | Local Runner STORM | Execute the requested runner, preserve the original topic, verify artifacts, and summarize outputs |
| "explore with me", "roundtable", "mind map", "let me steer" | Co-STORM | Interactive exploration with a conversation-local Co-STORM board and cited mind map |
| User provides local docs or a corpus | Corpus-restricted STORM | Use only provided material unless the user explicitly requests web research |
| "quick answer", "chat only", "no files" | Chat Brief STORM | In-chat concise report with citations and verification notes |

If the prompt is in Chinese, produce Chinese output by default while preserving English technical terms where they are standard.

## Classic STORM

1. Frame the topic and deliverable. Record audience, scope, recency needs, source limits, language, and expected depth. If absent and low-risk, choose conservative defaults and state them.
2. Plan sources before searching. Prefer primary papers, standards, official docs, and high-quality surveys; use vendor or marketing pages only for product-specific claims.
3. Generate perspectives. Always include `Basic fact writer`, then add up to three distinct writer personas that will ask different useful questions.
4. Run simulated interviews. For each perspective, repeat up to three turns: ask one non-repeated question, decompose it into up to three non-empty search queries, retrieve sources, and answer only from gathered information.
5. Build the information table. Log perspective, question, queries, source URL/title/date, snippets or evidence notes, supported claims, and reliability notes. Deduplicate by URL and claim.
6. Generate a draft outline directly from the topic, then refine it using the interview log. Use only `#`, `##`, and `###` headings. Do not include the topic itself as a heading.
7. Write sections from section-relevant evidence only. Use inline citations like `[1][2]` for factual claims.
8. Polish. Add a concise lead, remove duplication, keep the structure proportionate to the requested depth, reorder citations by first appearance, and preserve source traceability.

## Standard Artifact Contract

For non-interactive research, create exactly these four standard STORM artifacts under the requested output directory. If the user does not specify an output path, write them under `.results/<topic-slug>/`, where `<topic-slug>` is filesystem-safe and used only for the directory name:

1. `direct_gen_outline.<format>`: direct outline generated from the topic before evidence refinement.
2. `storm_gen_outline.<format>`: refined outline generated from the information-seeking interviews.
3. `storm_gen_article.<format>`: cited draft article written section by section from gathered evidence.
4. `storm_gen_article_polished.<format>`: final polished article with lead/summary, cleaned structure, references, and verification notes.

If the user does not specify a format, use `html`. If the user asks for `txt`, `md`, `markdown`, `pdf`, or another format, use that format where feasible and say what was produced. The base filenames above must remain unchanged; only the extension changes.

Example default paths for topic `调研 RAG 技术`:

- `.results/<topic-slug>/direct_gen_outline.html`
- `.results/<topic-slug>/storm_gen_outline.html`
- `.results/<topic-slug>/storm_gen_article.html`
- `.results/<topic-slug>/storm_gen_article_polished.html`

The final chat response should be short: list the four artifact paths, format, source/encoding verification, and any unresolved gaps. Do not paste the whole article into chat unless asked.

For local runner mode, map or convert runner outputs into the same four artifact names when possible. If the runner produces `.txt` but the user did not specify a format, convert the four standard outputs to `.html` after verifying UTF-8.

## Chat Brief Exception

Only use an in-chat brief when the user explicitly asks for a quick answer, no files, or chat-only output. In that case, return:

- `Research brief`: scope, assumptions, recency, and source boundaries.
- `Perspectives`: the writer personas used.
- `Question/query log`: compact table of questions, query themes, and source counts.
- `Refined outline`: final heading structure, capped to the requested depth.
- `Cited report`: concise synthesis with inline citations.
- `References`: numbered source list matching citation order.
- `Verification notes`: unsupported claims removed, stale-source risks, thin evidence, unresolved questions, and any retrieval/tool failures.

## Citation Rules

- Cite every factual, numeric, causal, legal, medical, financial, historical, or contested claim.
- Attribute disputes to the actor or source making the claim.
- Do not cite a source unless the gathered snippet or opened content directly supports the sentence.
- If evidence is insufficient, say what cannot be established instead of filling the gap.
- Prefer paraphrase; keep direct quotes short.
- Before finalizing, check that every citation number maps to exactly one source and every cited source appears in the reference list.

## Local Runner And File Hygiene

When using a local STORM implementation or writing artifacts:

- Keep the display topic separate from filename slugs. Never let ASCII filename sanitization replace a non-English research topic.
- If no output path is specified, create `.results/<topic-slug>/` and put all standard artifacts there.
- On Windows, force UTF-8 for Python stdout and file verification where possible, e.g. `PYTHONIOENCODING=utf-8`.
- Write text artifacts as UTF-8. HTML artifacts must include `<meta charset="utf-8">`. After generation, read each `.html`/`.txt`/`.md` artifact with strict UTF-8 and scan for common mojibake markers by code point, such as `U+FFFD`, `U+7039`, `U+6D93`, `U+9428`, `U+59AB`, `U+951B`, and repeated replacement-character or question-mark runs.
- If an existing tool writes legacy Windows encoding, convert the affected text artifacts to UTF-8 and verify by reading them back. Do not rely on terminal display alone.
- Filter blank generated search queries before sending them to a retriever. If a remote API resets the connection, reduce concurrency and retry once before reporting the blocker.
- Do not edit runner source code unless the user asks for a persistent fix; prefer process-local wrappers for one-off execution.

## Co-STORM Mode

Use Co-STORM only for explicitly interactive research: Co-STORM, collaborative exploration, roundtable discussion, user steering, or a mind map. Do not use it when the user only wants a finished report.

Co-STORM is conversation-first. Do not create the four standard STORM artifacts unless the user explicitly asks for file output. Keep the working state in a conversation-local Co-STORM board:

- `topic` and `scope`
- `current_focus`
- `observe_or_participate`: whether the user is currently observing, asking, or actively steering
- `discourse_history`: compact turn log of user, expert, specialist, and moderator utterances
- `participant_list`: active expert roles and why each role is useful now
- `open_questions`
- `mind_map`: hierarchical nodes with claims, uncertainty, and citation ids
- `sources`: numbered references in first-use order
- `unused_evidence_queue`: relevant retrieved snippets not yet used
- `assumptions_and_decisions`

Warm start with a mini Classic STORM pass: include `Basic fact writer`, add up to two focused specialists, run one interview turn per perspective, and use up to two non-empty search queries per turn. Organize the gathered evidence into the initial cited mind map before inviting user steering.

Use choice-first steering for user interaction. Ask one question at a time, prefer two or three meaningful multiple-choice options, put the recommended option first, and keep each option short enough to select by mouse click. In Codex or any environment with a native choice UI, call that UI directly; in Codex Desktop, use `request_user_input` when available. Do not render numeric-reply prompts when a native choice UI is available. Avoid broad open-ended questions unless the decision cannot be represented as useful choices.

For each interaction turn:

1. Incorporate the user's steering into `current_focus`.
2. Run a `ChooseIntent` step: question answering, question asking, moderator broadening, or final report.
3. Choose one role: general expert, rotating specialist, or moderator.
4. Use the Perspective-Guided Expert Pipeline for expert turns: generate a question or retrieve evidence, generate a cited response, polish the utterance, and update the mind map.
5. Use the Moderator Pipeline after two answer-only turns, repeated ground, narrow focus, or when unused evidence should be surfaced.
6. Show the user a compact update: answer, mind-map delta, open questions, and one choice-first steering prompt for suggested next directions.

Mind-map maintenance:

- Insert evidence under the node matching the question or query intent.
- Split overloaded nodes, merge duplicate nodes, and prune empty nodes.
- Mark uncertain or disputed claims instead of flattening them into facts.
- Keep citations attached to the smallest claim they support.

For DSPy-based local implementations, treat Co-STORM as a modular program blueprint: use Signatures for each step's typed inputs and outputs, Modules for `ChooseIntent`, expert response generation, moderator question generation, mind-map updates, and report generation, and Metrics to evaluate citation support, mind-map coverage, and turn usefulness before using DSPy optimizers.

When the user asks to conclude, summarize, or write the report, generate a final cited report from the mind map with references and verification notes. If the user explicitly asks for files, write `co_storm_mind_map.<format>` and `co_storm_report.<format>` under the requested output directory, or under `.results/<topic-slug>/` if no path is specified. If no format is specified for those files, use `html`.

## Completion Checks

- The final answer matches the requested depth: brief means synthesized, not a giant article; full article means complete and artifact-backed.
- The source set is appropriate for the domain and recency needs.
- The report includes enough research trace for the user to trust how it was made.
- Citations are in first-appearance order and support the surrounding claims.
- For default research requests, all four standard artifact files exist.
- If no output path was specified, those files are under `.results/`.
- If no format was specified, the four standard artifact files use `.html`.
- Artifact paths are listed and UTF-8 verification passed.
- Co-STORM runs maintain a cited mind map, expose open questions, and only write `co_storm_mind_map` / `co_storm_report` files when explicitly requested.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Searching broadly and summarizing immediately | Run perspective-guided questions first |
| Treating perspectives as stakeholder labels only | Make each perspective ask different questions |
| Using low-quality sources for core technical claims | Prefer papers, standards, official docs, and surveys |
| Writing an outline before evidence | Create a draft outline, then refine it from interview findings |
| Returning only a chat brief for normal research | Produce the four standard STORM artifact files by default |
| Using `.txt` when no format was specified | Default to `.html` |
| Producing an oversized outline for a brief prompt | Match article depth to the request, but still create the four artifacts |
| Dumping all sources into every section | Retrieve section-relevant snippets from the information table |
| Letting citations drift | Reorder citations by first appearance and verify every cited sentence |
| Losing non-English topics during filename sanitization | Preserve display topic; sanitize only the artifact path |
| Trusting terminal display for Chinese files | Read back as UTF-8 and scan for mojibake markers |
| Using Co-STORM by default | Use it only for explicit collaborative or mind-map requests |
| Writing the four standard artifacts for Co-STORM without a file request | Keep Co-STORM conversation-first; write only optional Co-STORM files when requested |

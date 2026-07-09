---
name: storm
description: Use when Codex needs STORM-style deep research, literature or background reviews, cited reports, multi-perspective source-grounded synthesis, or interactive Co-STORM-style exploration with roundtable or mind-map framing.
---

# STORM Research

## Overview

Use the Stanford STORM pattern for source-grounded research reports: generate diverse writer perspectives, run search-backed simulated interviews, refine an outline from the gathered evidence, write section by section with inline citations, then verify citations and gaps.

Default to classic STORM. Use Co-STORM mode only when the user explicitly asks for interactive exploration, roundtable discussion, collaboration, steering the research as it unfolds, or a mind map.

## Workflow Decision

| User intent | Use |
|---|---|
| "Research this", "write a cited report", "background/literature review", "multi-perspective synthesis" | Classic STORM |
| "Explore with me", "roundtable", "mind map", "interactive", "let me steer the discussion" | Co-STORM mode |
| User provides local docs or a corpus | Classic STORM, with retrieval restricted to the provided material unless web research is requested |

For detailed prompts, schemas, and checklists, read `references/storm-method.md`.

## Classic STORM

1. Frame the topic and deliverable. Record audience, scope, recency needs, source limits, and output length. If these are absent and not risky, choose conservative defaults and state them.
2. Generate perspectives. Always include `Basic fact writer`, then add up to three distinct writer personas inspired by adjacent topics or source categories.
3. Run simulated interviews. For each perspective, repeat up to three turns: ask one non-repeated writer question, decompose it into up to three search queries, retrieve sources, and answer only from gathered information.
4. Build the information table. Keep a log with perspective, question, queries, source URL/title/date, snippets, and supported claims. Deduplicate by URL and claim.
5. Generate a draft outline directly from the topic, then refine it using the interview log. Use only `#`, `##`, and `###` headings. Do not include the topic itself as a heading.
6. Write sections. For each first-level section, retrieve the most relevant snippets from the information table and write only that section. Use inline citations like `[1][2]` for factual claims.
7. Polish. Add a concise summary/lead, remove duplicate content if needed, reorder citations by first appearance, and preserve the article structure.

## Output Contract

Unless the user requests another format, return:

- `Research brief`: scope, assumptions, and source boundaries.
- `Perspectives`: the writer personas used.
- `Question/query log`: compact table of questions, queries, and source counts.
- `Refined outline`: final heading structure.
- `Cited report`: concise synthesis with inline citations.
- `References`: numbered source list matching citation order.
- `Verification notes`: unsupported claims removed, source gaps, stale-source risks, and unresolved questions.

## Citation Rules

- Cite every factual, numeric, causal, legal, medical, financial, historical, or contested claim.
- Attribute disputes to the actor or source making the claim.
- Do not cite a source unless its snippet or content directly supports the sentence.
- If no appropriate source is available, say the evidence is insufficient instead of filling the gap.
- Keep short quotes minimal; prefer paraphrase with citations.

## Co-STORM Mode

Use this mode only for explicitly interactive research. Warm start with a mini classic STORM pass, organize evidence into a hierarchical mind map, then alternate user turns, expert turns, and moderator questions. The moderator should introduce unused but relevant retrieved snippets when the discussion gets repetitive or too narrow. Generate the final report from the mind map.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Searching broadly and summarizing immediately | Run perspective-guided questions first |
| Treating perspectives as stakeholder labels only | Make each perspective ask different questions |
| Writing an outline before evidence | Create a draft outline, then refine it from interview findings |
| Dumping all sources into every section | Retrieve section-relevant snippets from the information table |
| Letting citations drift | Reorder citations by first appearance and verify every cited sentence |
| Using Co-STORM by default | Use it only for explicit collaborative or mind-map requests |

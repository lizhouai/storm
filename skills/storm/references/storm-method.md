# STORM Method Reference

## Contents

- Classic STORM algorithm
- Perspective generation
- Simulated interview loop
- Information table schema
- Outline generation
- Section writing
- Citation verification
- Co-STORM optional mode

## Classic STORM Algorithm

Use these defaults unless the user asks otherwise or the task risk calls for more depth:

| Parameter | Default |
|---|---:|
| Max non-basic perspectives | 3 |
| Max interview turns per perspective | 3 |
| Max search queries per turn | 3 |
| Search results per query | 3 |
| Section retrieval count | 3 |

Core sequence:

1. Generate perspectives.
2. Run one interview per perspective.
3. Convert all turns into an information table.
4. Generate a direct draft outline.
5. Refine the outline from the interview evidence.
6. Write each first-level section from section-relevant evidence.
7. Add lead/summary, remove duplicates if needed, and verify citations.

## Perspective Generation

Always include:

```text
Basic fact writer: Basic fact writer focusing on broadly covering the basic facts about the topic.
```

Generate additional perspectives by surveying adjacent topics, typical article structures, stakeholder groups, disciplines, controversies, historical context, technical dimensions, and affected communities.

Perspective prompt:

```text
I am writing a Wikipedia-like report on: {topic}

Identify up to three writer personas who would ask different useful questions.
Each persona should be a short role plus what it will focus on.
Avoid duplicates and avoid advocacy-only roles.
Return:
1. {role}: {focus}
2. {role}: {focus}
3. {role}: {focus}
```

Good perspectives are question-generating lenses, not just names. Prefer "regulatory historian focused on policy evolution" over "government perspective".

## Simulated Interview Loop

Run one interview per perspective. Each turn has four parts:

1. Writer asks one question.
2. Expert turns the question into search queries.
3. Retriever gathers source snippets.
4. Expert answers only from gathered information.

Writer question prompt:

```text
You are an experienced Wikipedia writer researching: {topic}
Your additional persona is: {persona}
Conversation so far:
{last_turns_or_NA}

Ask one useful question that has not already been asked.
If no useful question remains, say exactly:
Thank you so much for your help!
```

Query prompt:

```text
Topic: {topic}
Question: {question}

Write up to three search queries that would answer the question.
Return one query per line.
```

Grounded answer prompt:

```text
Topic: {topic}
Question: {question}
Gathered information:
{numbered_snippets}

Answer as an expert. Every sentence must be supported by the gathered information.
Use inline citations like [1][2].
If the information is insufficient, say what cannot be answered.
```

Stop a perspective interview after the writer thanks the expert, repeats questions, produces an empty question, or reaches the turn limit.

## Information Table Schema

Keep the research log in this shape:

| Field | Meaning |
|---|---|
| `perspective` | Writer persona |
| `turn` | Interview turn number |
| `question` | Writer question |
| `queries` | Search queries used |
| `source_id` | Temporary source number |
| `title` | Source title |
| `url` | Source URL or local document id |
| `date` | Publication or retrieval date when relevant |
| `snippet` | Supporting text or paraphrased evidence note |
| `claim_supported` | Claim this source can support |
| `reliability_note` | Primary/secondary, stale, weak, disputed, etc. |

Deduplicate sources by URL or document id. Deduplicate evidence by claim, but preserve distinct sources when a claim needs corroboration.

For user-provided local documents, use stable document ids instead of URLs and cite page/section names when available.

## Outline Generation

First create a direct draft outline from the topic alone. Then refine it using the information table. This prevents the final outline from being only a search-result summary while still grounding it in evidence.

Direct outline prompt:

```text
Write a Wikipedia-like outline for: {topic}
Use #, ##, and ### headings only.
Do not include the topic itself as a heading.
Do not include references, prose, or notes.
```

Refinement prompt:

```text
Topic: {topic}
Current outline:
{draft_outline}

Information-seeking interview findings:
{condensed_question_answer_log_without_citation_noise}

Improve the outline so it covers the important evidence and perspectives.
Use #, ##, and ### headings only.
Do not include the topic itself as a heading.
```

Outline checks:

- No standalone `Introduction` section unless the user asked for one.
- No `Conclusion`, `References`, or source-list heading in the outline.
- Sections are distinct enough to retrieve evidence separately.
- Contested or uncertain areas appear as attributed sections when important.

## Section Writing

Write one first-level section at a time. For each section:

1. Query the information table using the section heading and subsection headings.
2. Select the most relevant snippets.
3. Write only that section and its subsections.
4. Cite factual claims with local temporary citation numbers.
5. Merge the section into the article and remap citations globally.

Section prompt:

```text
Topic: {topic}
Section to write:
{section_outline}

Collected information:
{numbered_relevant_snippets}

Write only this section. Start with the section heading.
Use #, ##, and ### headings as appropriate.
Use inline citations like [1][2].
Do not include unrelated sections or a references list.
```

Skip separate `Introduction`, `Conclusion`, and `Summary` sections during section writing. Add a lead/summary in the polish step.

## Citation Verification

Before final output:

1. Build the numbered reference list in first-appearance order.
2. Check that every in-text `[n]` maps to exactly one source.
3. Check that every cited source is used in the report.
4. Remove unsupported citation numbers.
5. Remove or qualify unsupported claims.
6. Mark stale sources when date matters.
7. Add a limitations note when evidence is thin, contradictory, or not current.

Citation audit table:

| Citation | Claim | Source | Supports claim? | Action |
|---|---|---|---|---|
| `[1]` | ... | ... | yes/no/partial | keep/rewrite/remove |

## Co-STORM Optional Mode

Use only when the user asks for collaboration, roundtable discourse, interactive steering, or a mind map.

Co-STORM sequence:

1. Warm start with a mini STORM pass to collect background information.
2. Create a hierarchical knowledge base/mind map from cited information.
3. Generate initial experts from the topic and current focus.
4. Let the user inject questions or steering utterances.
5. On system turns, choose among general expert, rotating specialists, and moderator.
6. Use the moderator after several answer-only turns or when discussion gets narrow.
7. Insert cited information into the mind map by question/query intent.
8. Reorganize the mind map by expanding overloaded nodes and merging empty or single-child nodes.
9. Generate the final report from the mind map.

Moderator behavior:

- Look for relevant retrieved snippets that have not been used or cited.
- Prefer snippets close to the topic but not redundant with the last query.
- Ask one grounded question that naturally follows from the last turn.
- Cite the information that inspired the question.

Mind-map insertion options:

```text
insert
step: {existing child node}
create: {new child node}
```

Use classic STORM instead of Co-STORM when the user wants a single finished report and does not need to steer the research process.

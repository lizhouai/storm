# STORM Method Reference

## Contents

- Classic STORM algorithm
- Depth and deliverable defaults
- Standard artifact files
- Source selection ladder
- Perspective generation
- Simulated interview loop
- Information table schema
- Outline generation
- Section writing
- Citation verification
- Local runner mode
- Quality comparison heuristics
- Co-STORM interactive mode

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

## Depth and Deliverable Defaults

Choose the smallest deliverable that still preserves source-grounded reasoning.

| Request shape | Default depth | Notes |
|---|---|---|
| "调研一下", "research this", "survey the space" | Standard artifact bundle | Four files, default `.html`, concise-to-standard article depth |
| "technical review", "literature review", "决策建议" | Standard artifact bundle | Four files, default `.html`, more evaluation and tradeoffs |
| "Wikipedia-style", "完整长文", "generate article" | Full article | Full outline, section-by-section writing, artifact paths if saved |
| "run this STORM script/repo" | Local runner | Execute requested tool, then summarize and verify generated artifacts |
| "quick answer", "chat only", "no files" | Chat brief | In-chat report only |
| "Co-STORM", "roundtable", "mind map", "let me steer" | Co-STORM | Interactive cited mind map, then final report when requested |

For Chinese prompts, keep the final report in Chinese by default. Preserve standard English terms in parentheses when they help precision.

The standard artifact bundle is the default for non-interactive research. A concise article is not a failed STORM run, but it still needs the same four files so downstream tools can rely on stable artifact names.

Default output location:

1. If the user specifies an output path, write the artifacts there.
2. If the user does not specify an output path, create `.results/<topic-slug>/` and write all standard artifacts there.
3. Keep `display_topic` separate from `<topic-slug>`. The display topic is used for research and headings; the slug is only for the filesystem path.

## Standard Artifact Files

Create these four files for every non-interactive STORM research task unless the user explicitly asks for chat-only output:

| File | Stage | Required content |
|---|---|---|
| `direct_gen_outline.<format>` | Direct outline | Topic-only outline before evidence refinement |
| `storm_gen_outline.<format>` | Refined outline | Evidence-refined outline based on interview findings |
| `storm_gen_article.<format>` | Draft article | Section-by-section cited article generated from gathered evidence |
| `storm_gen_article_polished.<format>` | Polished article | Final article with lead/summary, cleaned structure, references, and verification notes |

Format rules:

1. If the user does not specify a format, use `html`.
2. If the user specifies `txt`, `md`, `markdown`, `pdf`, or another feasible format, keep the four base filenames and change only the extension.
3. HTML artifacts must be standalone UTF-8 files with `<meta charset="utf-8">`, a meaningful `<title>`, readable semantic headings, and citation links or citation text that works offline.
4. Do not replace the four files with a single combined report. A short run summary in chat is fine, but the files are the deliverable.
5. The default full paths are `.results/<topic-slug>/direct_gen_outline.html`, `.results/<topic-slug>/storm_gen_outline.html`, `.results/<topic-slug>/storm_gen_article.html`, and `.results/<topic-slug>/storm_gen_article_polished.html`.

Suggested HTML structure:

```html
<!doctype html>
<html lang="{language}">
<head>
  <meta charset="utf-8">
  <title>{topic} - {artifact_name}</title>
</head>
<body>
  <main>
    {artifact_content}
  </main>
</body>
</html>
```

For `storm_gen_article_polished.<format>`, include sections for references and verification notes at the end. For the outline files, include only outline content plus minimal metadata such as topic and generation stage.

## Source Selection Ladder

Use sources according to claim type:

| Claim type | Preferred sources |
|---|---|
| Definitions, algorithms, benchmark claims | Original papers, peer-reviewed venues, arXiv papers when clearly identified |
| Current standards, safety risks, governance | Official standards bodies, OWASP/NIST/vendor security docs, recent surveys |
| Product capabilities | Official product documentation or release notes |
| Ecosystem trends | High-quality surveys first; reputable technical blogs only as secondary color |

Avoid letting a search engine's top results define the outline. Use retrieved evidence to refine a topic-driven outline, not replace it with a source-result collage.

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

If a generated search query is empty or only punctuation, discard it. If all queries for a turn are empty, ask the writer to reformulate once; if it remains empty, stop that perspective and record the gap.

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
- The number of headings fits the deliverable depth. A concise artifact bundle should not receive an oversized encyclopedia outline.

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

## Local Runner Mode

Use this section when the user explicitly asks to run a local STORM implementation, script, virtual environment, or existing pipeline.

Execution principles:

1. Inspect the runner's CLI before running it. Confirm how the topic is supplied.
2. Preserve two topic values:
   - `display_topic`: the exact user topic used for research and prompts.
   - `artifact_slug`: a filesystem-safe slug used only for directories and filenames.
3. If no output path is specified, set or move final artifacts to `.results/<artifact_slug>/`.
4. For non-English topics, do not pass a sanitized ASCII slug as the research topic. If the runner conflates topic and directory name, wrap it process-locally or patch only when the user asks for a persistent fix.
5. Start with the requested parameters. If the run fails due to connection reset or rate limits, reduce concurrency and retry once.
6. Filter empty generated retriever queries before sending them to APIs when a process-local wrapper can safely do so.
7. After a successful run, map or convert the runner outputs into the standard four artifact files. If no format was specified, convert the four standard outputs to HTML.
8. List output files, run parameters, timing/token usage if available, and any warnings that may affect trust.

Windows and encoding hygiene:

1. Set Python stdout to UTF-8 when printing Chinese or other non-ASCII text.
2. HTML artifacts must include `<meta charset="utf-8">`.
3. Read each generated `.html`, `.txt`, and `.md` artifact back with strict UTF-8.
4. Scan for mojibake markers by code point, such as `U+FFFD`, `U+7039`, `U+6D93`, `U+9428`, `U+59AB`, `U+93B6`, `U+951B`, repeated replacement-character runs, or repeated question-mark runs.
5. If files were written in GBK/GB18030, convert only affected text artifacts to UTF-8, then verify by reading them back.
6. Do not trust `Get-Content` or terminal preview alone; terminal decoding can make good files look bad or bad files look good.

When reporting local runner results, include whether the source tree was modified. Prefer no source edits for one-off execution.

## Quality Comparison Heuristics

When comparing a manual STORM brief with a full local STORM article, judge them by the intended deliverable:

| Dimension | Brief should optimize | Full article should optimize |
|---|---|---|
| Synthesis | Clear takeaways and decisions | Breadth and section coverage |
| Traceability | Compact query/source log | Complete intermediate artifacts |
| Citations | High-quality, first-appearance references | Dense coverage across sections |
| Readability | Low duplication and strong prioritization | Navigable outline and complete prose |
| Risk disclosure | Explicit gaps and stale-source notes | Run logs, raw retrieval, and artifact verification |

A longer article is not automatically better. Default STORM should still create the four standard files; adjust article length inside those files according to the user's request.

## Co-STORM Interactive Mode

Use Co-STORM only when the user asks for collaboration, roundtable discourse, interactive steering, or a mind map. Use Classic STORM instead when the user wants one finished report and does not need to steer the research process.

Co-STORM is conversation-first. It maintains a conversation-local Co-STORM board and a cited mind map during the discussion. It does not create the four standard STORM artifacts unless the user explicitly requests file output.

### Warm Start Defaults

Run a mini Classic STORM pass before the first open-ended user steering prompt:

| Parameter | Default |
|---|---:|
| Required perspective | `Basic fact writer` |
| Additional specialists | Up to 2 |
| Interview turns per perspective | 1 |
| Search queries per turn | Up to 2 |
| Search results per query | Up to 3 |

The warm start should identify the initial scope, obvious subtopics, evidence-backed facts, disputed points, and promising questions. Preserve all source-grounding rules from Classic STORM.

### Co-STORM Board Schema

Maintain this board in the conversation context and update it after each system turn:

```yaml
co_storm_board:
  topic: "{display topic}"
  scope: "{current boundaries and exclusions}"
  current_focus: "{active branch or question}"
  open_questions:
    - id: Q1
      question: "{unresolved question}"
      priority: high|medium|low
  mind_map:
    - node: "{topic branch}"
      claims:
        - claim: "{evidence-backed claim}"
          citations: ["[1]"]
          status: supported|partial|disputed|uncertain
      children: []
  sources:
    - id: "[1]"
      title: "{source title}"
      url_or_doc_id: "{url or local document id}"
      date: "{publication or retrieval date when relevant}"
      reliability_note: "{primary, secondary, stale, weak, disputed, etc.}"
  unused_evidence_queue:
    - source_id: "[2]"
      note: "{relevant snippet or evidence note not yet used}"
      suggested_node: "{where it may fit}"
  assumptions_and_decisions:
    - "{scope choice, user preference, or unresolved limitation}"
```

When the board is too large to show in full, keep the full board mentally in context and show only a compact delta plus the most relevant branch.

### Choice-First Steering

Borrow the interaction style from the brainstorming skill: keep the user in flow by asking one question at a time and making the next move selectable.

Use choice-first steering whenever Co-STORM needs user direction:

- Ask one question at a time.
- Prefer two or three meaningful multiple-choice options.
- Put the recommended option first and label it as recommended when the UI supports labels.
- Each option should be a real tradeoff or research path, not filler.
- Keep labels short enough for a mouse click and descriptions to one sentence.
- Use a native choice UI when available so the user can continue with a mouse click.
- In Codex Desktop, use `request_user_input` when that tool is available.
- Do not render numeric-reply prompts in environments that support native choice UI.
- If no native choice UI exists, show compact labeled options and briefly state that clickable choices are unavailable in the current environment.
- Do not include a generic `Other` option when the native UI already provides free-form input.
- Use open-ended questions only when meaningful choices would hide the real ambiguity.

Choice prompt shape:

```yaml
choice_prompt:
  question: "{single steering question}"
  options:
    - label: "{recommended short label}"
      description: "{one-sentence impact or tradeoff}"
      recommended: true
    - label: "{second short label}"
      description: "{one-sentence impact or tradeoff}"
      recommended: false
    - label: "{third short label}"
      description: "{one-sentence impact or tradeoff}"
      recommended: false
  freeform_allowed: true|false
```

Good Co-STORM steering questions decide the next research move, such as deepen the current branch, broaden to a neighboring branch, compare two claims, invite a moderator, or produce the final report. Avoid asking "what next?" without options.

### Turn Protocol

For each Co-STORM turn:

1. Interpret the user's latest steering utterance and update `current_focus`.
2. Select exactly one role for the response:
   - `general expert` for broad synthesis across the mind map.
   - `specialist` for a specific technical, historical, market, policy, or methodological branch.
   - `moderator` for broadening, reconnecting branches, or surfacing unused evidence.
3. Retrieve or inspect more evidence only when the current board is insufficient.
4. Answer from cited evidence, explicitly marking uncertain or unsupported points.
5. Insert new evidence into the mind map under the node matching the question or query intent.
6. Return a compact response with:
   - `Answer`
   - `Mind-map update`
   - `Open questions`
   - `Choice-first steering prompt`

Do not ask the user to confirm obvious next exploration steps. Offer concrete next directions and continue when the user picks one or asks a follow-up.

### Moderator Behavior

Use the moderator after two answer-only turns, when the discussion repeats, when it follows a single narrow branch for too long, or when the unused evidence queue contains relevant material.

The moderator should:

- Look for relevant retrieved snippets that have not been used or cited.
- Prefer evidence close to the topic but not redundant with the last answer.
- Ask one grounded question that naturally follows from the current mind map.
- Cite the information that inspired the question.
- Suggest whether to deepen, broaden, compare, or summarize next.

### Mind-Map Maintenance

Insertion options:

```text
insert: add evidence to an existing node
create: create a new child node
split: divide an overloaded node into clearer child nodes
merge: combine duplicate or near-empty sibling nodes
prune: remove empty nodes that carry no claim or open question
```

Rules:

- Attach citations to the smallest claim they support.
- Keep disputed claims as separate attributed claims instead of smoothing over disagreement.
- Preserve local document ids and page or section names when using a provided corpus.
- Expand overloaded nodes before adding more citations to them.
- Merge empty or single-child nodes only when the merge does not hide an important distinction.

### Final Report

Generate the final report when the user asks to conclude, summarize, produce an article, or write the report. The report should be built from the mind map, not from a fresh unstructured summary.

Include:

- Scope and assumptions.
- Synthesized answer organized by the final mind-map structure.
- Inline citations in first-appearance order.
- References.
- Verification notes covering unsupported claims removed, disputed evidence, stale-source risks, thin branches, and retrieval failures.

If the user explicitly asks for files, create:

- `co_storm_mind_map.<format>`
- `co_storm_report.<format>`

Use the requested output directory, or `.results/<topic-slug>/` if no path is specified. If no format is specified, use `html`. HTML files must follow the same UTF-8 and offline-readable requirements as standard STORM artifacts.

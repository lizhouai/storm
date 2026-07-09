# STORM Research Skill

Current version: `v0.2.0`

An Agent Skill for STORM-style deep research: perspective-guided interviews, source-grounded synthesis, structured outlines, inline citations, and verification notes.

This skill packages the Stanford STORM research pattern as a reusable workflow for coding agents that support `SKILL.md`-based Agent Skills. It is based on the original [stanford-oval/storm](https://github.com/stanford-oval/storm) project.

## What It Does

Use `storm` when you want an agent to produce standard STORM research artifacts instead of a shallow summary.

It helps the agent:

- define the research scope, audience, assumptions, and source boundaries
- generate multiple writer perspectives, including a basic fact writer
- run search-backed simulated interviews from each perspective
- collect evidence into an information table
- refine an outline from the gathered evidence
- write the standard STORM files: `direct_gen_outline`, `storm_gen_outline`, `storm_gen_article`, and `storm_gen_article_polished`
- default to HTML artifacts when no output format is specified
- write section-by-section with inline citations
- verify citation coverage, unsupported claims, source gaps, and stale-source risks

The default mode is classic STORM. Co-STORM mode is available for interactive exploration, roundtable-style discussion, or mind-map driven research.

## Install

Install with:

```bash
npx skills add lizhouai/storm
```

## Usage

Ask your agent to use the `storm` skill. In Codex, you can call it explicitly:

```text
$storm Research the current state of AI code review tools.
```

By default this creates four HTML files under `.results/<topic-slug>/`:

- `.results/<topic-slug>/direct_gen_outline.html`
- `.results/<topic-slug>/storm_gen_outline.html`
- `.results/<topic-slug>/storm_gen_article.html`
- `.results/<topic-slug>/storm_gen_article_polished.html`

To use another format, ask for it explicitly:

```text
$storm 调研一下 RAG 技术，输出 markdown 格式
```

General agent prompt:

```text
Use the storm skill to write a source-grounded background review of open-source LLM evaluation frameworks.
```

Co-STORM style exploration:

```text
Use storm in Co-STORM mode to explore commercial paths for embodied AI. Start with a roundtable and maintain a mind-map style structure.
```

Local-document constrained research:

```text
Use storm to synthesize the documents in this repository. Restrict retrieval to the provided material unless web research is explicitly needed.
```

## Output Format

Unless you request another format, the skill produces a standard STORM artifact bundle in HTML under `.results/<topic-slug>/`:

- `direct_gen_outline.html`: topic-only outline before evidence refinement
- `storm_gen_outline.html`: evidence-refined outline
- `storm_gen_article.html`: cited draft article
- `storm_gen_article_polished.html`: polished final article with references and verification notes

If you explicitly ask for chat-only or no files, the skill can instead return a compact in-chat brief with perspectives, query log, citations, references, and verification notes.

## When To Use It

Good fit:

- research reports
- background reviews
- literature reviews
- competitive or market scans
- technical landscape summaries
- source-grounded policy or historical synthesis
- multi-perspective explanations of contested topics

Less useful for:

- quick factual lookups
- tasks where no citations are needed
- implementation work that mainly needs code changes
- unsupported speculation or opinion writing

## Workflow

Classic STORM follows this sequence:

1. Frame the topic and deliverable.
2. Generate writer perspectives.
3. Run simulated interviews for each perspective.
4. Build an information table from gathered evidence.
5. Draft and refine the outline.
6. Write `direct_gen_outline.<format>`, `storm_gen_outline.<format>`, `storm_gen_article.<format>`, and `storm_gen_article_polished.<format>`.
7. Polish, reorder citations, verify claims, and check artifact encoding.

Co-STORM is only used when you explicitly ask for interactive exploration, roundtable discussion, user steering, or a mind map.

## Repository Structure

```text
storm/
  README.md
  LICENSE
  skills/
    storm/
      SKILL.md
      agents/
        openai.yaml
      references/
        storm-method.md
```

- `skills/storm/SKILL.md` is the skill entry point and activation contract.
- `skills/storm/references/storm-method.md` contains the detailed algorithm, prompts, schemas, and quality checks.
- `skills/storm/agents/openai.yaml` provides display metadata for OpenAI-style agent surfaces.
- The repository root intentionally does not contain `SKILL.md`, so `npx skills add lizhouai/storm` installs the full `skills/storm/` bundle instead of a single file.

## Compatibility

This repository uses the Agent Skills `SKILL.md` format. It is intended to work with any agent or tool that can install or read skills in this format, including environments managed through the `npx skills` CLI.

Different agents expose skills differently. If explicit invocation syntax is unavailable, ask the agent in natural language to "use the storm skill".

## Updating

Update an installed copy with:

```bash
npx skills update storm -g
```

Or reinstall from the repository:

```bash
npx skills add lizhouai/storm -g --copy
```

## Development

Clone the repository:

```bash
git clone https://github.com/lizhouai/storm.git
cd storm
```

Validate local discovery:

```bash
npx skills add . --list
```

Install your local working copy while developing:

```bash
npx skills add . -g --copy
```

## License

MIT License. See [LICENSE](LICENSE).

The original [stanford-oval/storm](https://github.com/stanford-oval/storm) project is also released under the MIT License.

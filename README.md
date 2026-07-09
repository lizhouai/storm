# STORM Research Skill

[![Release](https://img.shields.io/github/v/release/lizhouai/storm?label=release&style=for-the-badge&labelColor=555555&color=007ec6&cacheSeconds=300)](https://github.com/lizhouai/storm/releases/latest)
[![License](https://img.shields.io/github/license/lizhouai/storm?label=license&style=for-the-badge&labelColor=555555&color=97ca00)](LICENSE)

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
- write section-by-section with inline citations
- produce the standard STORM artifact bundle
- verify citation coverage, unsupported claims, source gaps, and stale-source risks

The default mode is classic STORM. Co-STORM mode is available for interactive exploration, roundtable discussion, user steering, and mind-map driven research.

## Install

Install with:

```bash
npx skills add lizhouai/storm --full-depth
```

## Usage

Ask your agent to use the `storm` skill. In Codex, you can call it explicitly:

```text
$storm Research the current state of AI code review tools.
```

By default this creates the standard HTML artifact bundle under `.results/<topic-slug>/`. See [Output Format](#output-format).

To use another format, ask for it explicitly:

```text
$storm Research RAG technology and output markdown format
```

General agent prompt:

```text
Use the storm skill to write a source-grounded background review of open-source LLM evaluation frameworks.
```

Co-STORM style exploration:

```text
Use storm in Co-STORM mode to explore commercial paths for embodied AI. Start with a roundtable and maintain a mind-map style structure.
```

In Co-STORM mode, the agent keeps a conversation-local Co-STORM board with a cited mind map, discourse history, participants, open questions, sources, unused evidence, and current focus. It uses choice-first steering: one question at a time, two or three meaningful options, and the native choice UI when available so you can keep steering with a mouse click. The turn manager chooses whether the next move is expert answering, expert question asking, moderator broadening, or final report generation. When you ask to conclude or write the report, it generates a final cited report from that board.

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

Co-STORM is conversation-first and does not create the four standard STORM files unless you explicitly ask for file output. If you do request files, it writes:

- `co_storm_mind_map.<format>`: the cited mind map and open questions
- `co_storm_report.<format>`: the final report synthesized from the mind map

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
6. Write the standard artifact bundle.
7. Polish, reorder citations, verify claims, and check artifact encoding.

Co-STORM is used when you explicitly ask for interactive exploration, roundtable discussion, user steering, or a mind map. It starts with a mini STORM warm start, maintains a cited mind map during the conversation, tracks discourse history, asks click-style steering questions one at a time, and writes the final report when you ask to conclude. For local runner implementations, the method reference includes a DSPy module blueprint based on Signatures, Modules, Metrics, and optional Optimizers.

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
- The repository root intentionally does not contain `SKILL.md`; use `--full-depth` so the skills CLI discovers the full `skills/storm/` bundle.

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
npx skills add lizhouai/storm -g --copy --full-depth
```

## Development

Clone the repository:

```bash
git clone https://github.com/lizhouai/storm.git
cd storm
```

Validate local discovery:

```bash
npx skills add . --list --full-depth
```

Install your local working copy while developing:

```bash
npx skills add . -g --copy --full-depth
```

## License

MIT License. See [LICENSE](LICENSE).

The original [stanford-oval/storm](https://github.com/stanford-oval/storm) project is also released under the MIT License.

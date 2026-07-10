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

The default mode is classic STORM. A prompt-native Co-STORM preview is available for interactive exploration, roundtable discussion, user steering, and mind-map driven research. It is an agent workflow, not a bundled `knowledge-storm` runner.

## Install

Install with:

```bash
npx skills add lizhouai/storm
```

This installs the skill for the current project. Add `-g` only when you intentionally want a global installation, and use the same scope when updating.

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

Prompt-native Co-STORM preview:

```text
Use the prompt-native Co-STORM preview to explore commercial paths for embodied AI. Start with a roundtable and maintain a mind-map style structure.
```

In the Co-STORM preview, the agent keeps a conversation-local board with a cited mind map, discourse history, participants, open questions, sources, unused evidence, and current focus. It uses choice-first steering and routes each turn to an expert, specialist, moderator, or final-report step. Compact checkpoints make the board recoverable when the host preserves conversation state; if state or citation mappings are lost, the agent must disclose the gap and rebuild them before continuing.

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

The Co-STORM preview is conversation-first and does not create the four standard STORM files unless you explicitly ask for file output. If you do request files, it writes:

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

The prompt-native Co-STORM preview is used only when you explicitly ask for interactive exploration, roundtable discussion, user steering, or a mind map. It starts with a mini STORM warm start, maintains a cited mind map and checkpoint during the conversation, and writes the final report when you ask to conclude. The method reference includes a DSPy implementation blueprint, but this repository does not bundle DSPy modules or an executable Co-STORM runner.

## Repository Structure

```text
storm/
  README.md
  LICENSE
  CONTRIBUTING.md
  evals/
    cases.json
  scripts/
    validate_skill.py
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
- `evals/cases.json` defines manual forward-eval fixtures for critical modes and safety boundaries.
- `scripts/validate_skill.py` enforces the repository contract without third-party Python dependencies.
- The repository root intentionally does not contain `SKILL.md`; the standard `skills/storm/` layout lets the skills CLI install the whole bundle.

## Compatibility

This repository uses the Agent Skills `SKILL.md` format. Local discovery and bundle installation are validated with the `npx skills` CLI. Other compatible agents can read the same skill, but tool availability, native choice UI, and automatic triggering vary by host.

Different agents expose skills differently. If explicit invocation syntax is unavailable, ask the agent in natural language to "use the storm skill".

## Updating

Update a project-local installation with:

```bash
npx skills update storm
```

For a global installation, use the matching global scope:

```bash
npx skills update storm -g
```

## Development

Clone the repository:

```bash
git clone https://github.com/lizhouai/storm.git
cd storm
```

Run the repository checks and validate local discovery:

```bash
python scripts/validate_skill.py
npx skills add . --list
```

Install your local working copy while developing:

```bash
npx skills add . -g --copy
```

## License

MIT License. See [LICENSE](LICENSE).

The original [stanford-oval/storm](https://github.com/stanford-oval/storm) project is also released under the MIT License. See the original [STORM paper](https://aclanthology.org/2024.naacl-long.347/) and [Co-STORM paper](https://aclanthology.org/2024.emnlp-main.554/) for the research systems this prompt-native skill adapts.

# STORM Research Skill

An Agent Skill for STORM-style deep research: perspective-guided interviews, source-grounded synthesis, structured outlines, inline citations, and verification notes.

This skill packages the Stanford STORM research pattern as a reusable workflow for coding agents that support `SKILL.md`-based Agent Skills.

## What It Does

Use `storm` when you want an agent to produce a careful research brief instead of a shallow summary.

It helps the agent:

- define the research scope, audience, assumptions, and source boundaries
- generate multiple writer perspectives, including a basic fact writer
- run search-backed simulated interviews from each perspective
- collect evidence into an information table
- refine an outline from the gathered evidence
- write section-by-section with inline citations
- verify citation coverage, unsupported claims, source gaps, and stale-source risks

The default mode is classic STORM. Co-STORM mode is available for interactive exploration, roundtable-style discussion, or mind-map driven research.

## Install

Install globally for your current agent:

```bash
npx skills add lizhouai/storm -g
```

Install globally for all supported agents detected on your machine:

```bash
npx skills add lizhouai/storm -g --all
```

Preview the skill before installing:

```bash
npx skills add lizhouai/storm --list
```

Install into the current project instead of globally:

```bash
npx skills add lizhouai/storm
```

If symlinks are inconvenient on your system, copy the files instead:

```bash
npx skills add lizhouai/storm -g --all --copy
```

## Usage

Ask your agent to use the `storm` skill. In Codex, you can call it explicitly:

```text
$storm Research the current state of AI code review tools. Write a concise Chinese report with perspectives, citations, and verification notes.
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

Unless you request another format, the skill guides the agent toward this structure:

- Research brief: scope, assumptions, and source boundaries
- Perspectives: writer personas used during research
- Question/query log: compact table of interview questions, queries, and source counts
- Refined outline: final heading structure
- Cited report: source-grounded synthesis with inline citations
- References: numbered source list matching first citation order
- Verification notes: unsupported claims removed, gaps, stale-source risks, and unresolved questions

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
6. Write sections from section-relevant evidence.
7. Polish, reorder citations, and verify claims.

Co-STORM is only used when you explicitly ask for interactive exploration, roundtable discussion, user steering, or a mind map.

## Repository Structure

```text
storm/
  SKILL.md
  README.md
  agents/
    openai.yaml
  references/
    storm-method.md
```

- `SKILL.md` is the skill entry point and activation contract.
- `references/storm-method.md` contains the detailed algorithm, prompts, schemas, and quality checks.
- `agents/openai.yaml` provides display metadata for OpenAI-style agent surfaces.

## Compatibility

This repository uses the Agent Skills `SKILL.md` format. It is intended to work with agents and tools that can install or read Agent Skills, including Codex-compatible skill directories and the `npx skills` CLI.

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

No license file is included yet. Add a license before relying on this repository for public redistribution or downstream reuse.

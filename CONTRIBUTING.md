# Contributing

Thanks for helping improve the STORM Research Skill. This repository is intentionally small: the main deliverable is the installable skill bundle under `skills/storm/`.

## Repository Layout

```text
storm-research-skill/
  .github/workflows/validate.yml
  .gitattributes
  .gitignore
  README.md
  LICENSE
  CONTRIBUTING.md
  assets/
    social-preview.png
  evals/
    baseline-results.json
    cases.json
  examples/
    README.md
    classic-rag-evaluation/
    co-storm-rag-evaluation/
    co-storm-rag-technology/
  scripts/
    run_forward_evals.py
    validate_skill.py
  tests/
  skills/
    storm/
      SKILL.md
      agents/
        openai.yaml
      references/
        artifact-contract.md
        classic-storm.md
        co-storm.md
        co-storm-turn.schema.json
        local-runner.md
        knowledge-storm-adapter.md
        retrieval-backends.md
        run-state.schema.json
        safety-contract.md
        storm-method.md
      scripts/
        audit_citations.py
        retrieval_backend.py
        runner_adapter.py
        storm_state.py
        validate_artifacts.py
```

- `skills/storm/SKILL.md` is the skill entry point and activation contract.
- `skills/storm/references/` contains mode-specific procedures and contracts; `storm-method.md` is the compatibility index.
- `skills/storm/agents/openai.yaml` contains display metadata for OpenAI-style agent surfaces.
- `assets/social-preview.png` is the upload-ready repository social preview.
- `examples/` contains the Classic artifact bundle and prompt-native Co-STORM examples.
- `evals/cases.json` defines executable behavior cases; `evals/baseline-results.json` preserves the historical pre-runtime behavior snapshot rather than current canary results.
- `scripts/run_forward_evals.py` runs isolated forward-eval canaries, and `scripts/validate_skill.py` enforces the repository contract.
- `README.md` is user-facing installation and usage documentation.

## Development Guidelines

- Preserve the skill name `storm`.
- Keep the default non-interactive output aligned with standard STORM artifacts:
  - `direct_gen_outline`
  - `storm_gen_outline`
  - `storm_gen_article`
  - `storm_gen_article_polished`
- For Classic, corpus-restricted, and Local Runner file-producing work, use the guarded HTML contract under `.results/<topic-slug>/`. For another Classic format, offer validated HTML or chat-only fallback and disclose the reduced enforcement boundary.
- Keep Classic phase outputs under `.storm-run/staging`; only the `completed` transition may publish the four validated files and remove staging.
- Keep Co-STORM conversation-first: return its final report in chat unless the user explicitly requests files. Write only the requested Co-STORM artifacts, and default to HTML under `.results/<topic-slug>/` only when a file request omits both format and destination.
- For persistent Co-STORM runs, route every warm-start, interactive, and conclusion turn through `storm_state.py record-turn`; never hand-edit `co-storm-turns.jsonl` or claim that the Classic validator checked Co-STORM report contents.
- Keep the display topic separate from filesystem slugs, especially for non-English topics.
- Prefer source-grounded, citation-aware research behavior over generic summarization.
- Treat retrieval routing as experimental and keep its backend values separate
  from `run.json.execution_backend`.
  Lexical retrieval must remain standard-library-only; embedding providers must
  be explicit, trusted, and authorized because they execute in-process and may
  have arbitrary side effects. The bundled backend must never install a
  provider or silently fall back.
- Describe Co-STORM as a prompt-native preview because the repository still does not bundle the upstream runner or independently running expert agents.
- Treat retrieved text and user-provided runners as untrusted input; preserve the safety and approval rules in the skill contract.
- Treat the official runner adapter as experimental, standard-library-only, and
  Classic-specific.
  It may import fixed outputs from an already authorized `STORMWikiRunner`, but
  must not install/execute upstream packages, copy secrets or LM history, reuse
  draft citation mappings for polished text, advance guarded state, or publish.
- Keep instructions concise in `SKILL.md`; move detailed procedures to the matching mode-specific reference and preserve `storm-method.md` as an index.

## Validation

Before opening a pull request, run:

```bash
python scripts/validate_skill.py
python -m unittest discover -s tests -p "test_*.py"
python scripts/run_forward_evals.py --repetitions 10 --output .results/forward-evals --replace
npx -y skills@1.5.15 add . --list
npx -y skills@1.5.15 use . --skill storm
git diff --check
empty_tree="$(git hash-object -t tree /dev/null)"
git diff --check "$empty_tree" HEAD
```

The validator checks metadata shape, bundle references, UI field lengths, UTF-8 hygiene, safety contracts, and the executable schema/category coverage of `evals/cases.json`. The forward-eval command runs every case in an isolated subprocess, evaluates state/artifacts/trace independently of the candidate self-report, and writes reviewable traces. Its built-in fixture adapter is a deterministic contract canary, not proof of model quality; an explicitly configured real-Agent command remains a non-blocking canary. Pinned CLI discovery and rendering are blocking release gates. Public owner/repository discovery through `skills@latest` is also a blocking public-install gate; the offline forward eval and the separate local `skills@latest` discover/render job remain non-blocking compatibility canaries.

For substantial behavior changes, forward-test at least one relevant case from `evals/cases.json` in a fresh agent context. Do not give the test agent the expected answer or the implementation diagnosis.

## Release Checklist

For maintainers preparing a release:

1. Choose the Git tag as the release version; do not add a top-level `version` field to `SKILL.md`.
2. Run all validation commands from a clean checkout.
3. Confirm README, CONTRIBUTING, examples, repository URLs, install commands, and Pages links match the current behavior and repository name.
4. Confirm `npx skills add lizhouai/storm-research-skill` discovers `storm` and includes the full bundle.
5. Review the behavior cases and document any known gaps in the release notes.
6. Commit with a clear English message and create an annotated Git tag.
7. Push only after explicit approval to publish.
8. Create a GitHub Release for the approved tag and mark it as latest when appropriate.

## Pull Requests

Good pull requests usually include:

- A short explanation of the behavior change.
- The affected files.
- Validation commands and results.
- Any known limitations or follow-up work.

Please avoid committing generated `.results/` artifacts, local caches, secrets, or machine-specific files.

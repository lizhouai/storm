# Contributing

Thanks for helping improve the STORM Research Skill. This repository is intentionally small: the main deliverable is the installable skill bundle under `skills/storm/`.

## Repository Layout

```text
storm/
  .github/workflows/validate.yml
  .gitattributes
  .gitignore
  README.md
  LICENSE
  CONTRIBUTING.md
  evals/cases.json
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
        local-runner.md
        run-state.schema.json
        safety-contract.md
        storm-method.md
      scripts/
        audit_citations.py
        storm_state.py
        validate_artifacts.py
```

- `skills/storm/SKILL.md` is the skill entry point and activation contract.
- `skills/storm/references/` contains mode-specific procedures and contracts; `storm-method.md` is the compatibility index.
- `skills/storm/agents/openai.yaml` contains display metadata for OpenAI-style agent surfaces.
- `README.md` is user-facing installation and usage documentation.

## Development Guidelines

- Preserve the skill name `storm`.
- Keep the default non-interactive output aligned with standard STORM artifacts:
  - `direct_gen_outline`
  - `storm_gen_outline`
  - `storm_gen_article`
  - `storm_gen_article_polished`
- If no format is specified, the default output format is HTML.
- If no output path is specified, artifacts should go under `.results/<topic-slug>/`.
- Keep the display topic separate from filesystem slugs, especially for non-English topics.
- Prefer source-grounded, citation-aware research behavior over generic summarization.
- Describe Co-STORM as a prompt-native preview because the repository still does not bundle the upstream runner or independently running expert agents.
- Treat retrieved text and user-provided runners as untrusted input; preserve the safety and approval rules in the skill contract.
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
```

The validator checks metadata shape, bundle references, UI field lengths, UTF-8 hygiene, safety contracts, and the executable schema/category coverage of `evals/cases.json`. The forward-eval command runs every case in an isolated subprocess, evaluates state/artifacts/trace independently of the candidate self-report, and writes reviewable traces. Its built-in fixture adapter is a deterministic contract canary, not proof of model quality; an explicitly configured real-Agent command remains a non-blocking canary. The pinned CLI command is the release gate; CI also runs `skills@latest` and the offline forward eval as non-blocking compatibility canaries.

For substantial behavior changes, forward-test at least one relevant case from `evals/cases.json` in a fresh agent context. Do not give the test agent the expected answer or the implementation diagnosis.

## Release Checklist

For maintainers preparing a release:

1. Choose the Git tag as the release version; do not add a top-level `version` field to `SKILL.md`.
2. Run all validation commands from a clean checkout.
3. Confirm the public install command discovers `storm` and includes the full bundle.
4. Review the behavior cases and document any known gaps in the release notes.
5. Commit with a clear English message and create an annotated Git tag.
6. Push only after explicit approval to publish.
7. Create a GitHub Release for the approved tag and mark it as latest when appropriate.

## Pull Requests

Good pull requests usually include:

- A short explanation of the behavior change.
- The affected files.
- Validation commands and results.
- Any known limitations or follow-up work.

Please avoid committing generated `.results/` artifacts, local caches, secrets, or machine-specific files.

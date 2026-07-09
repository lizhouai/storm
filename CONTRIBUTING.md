# Contributing

Thanks for helping improve the STORM Research Skill. This repository is intentionally small: the main deliverable is the installable skill bundle under `skills/storm/`.

## Repository Layout

```text
storm/
  README.md
  LICENSE
  CONTRIBUTING.md
  skills/
    storm/
      SKILL.md
      agents/
        openai.yaml
      references/
        storm-method.md
```

- `skills/storm/SKILL.md` is the skill entry point and activation contract.
- `skills/storm/references/storm-method.md` contains the detailed STORM workflow, prompts, artifact rules, and quality checks.
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
- Keep instructions concise in `SKILL.md`; move detailed procedures to `references/storm-method.md`.

## Validation

Before opening a pull request, run:

```bash
git diff --check
```

Also verify the skill metadata and key output contract are still present:

```bash
python - <<'PY'
from pathlib import Path

skill = Path("skills/storm/SKILL.md").read_text(encoding="utf-8")
method = Path("skills/storm/references/storm-method.md").read_text(encoding="utf-8")
combined = skill + "\n" + method

required = [
    "name: storm",
    "direct_gen_outline",
    "storm_gen_outline",
    "storm_gen_article",
    "storm_gen_article_polished",
    ".results/<topic-slug>/",
    "If the user does not specify a format, use `html`",
]

missing = [item for item in required if item not in combined]
if missing:
    raise SystemExit(f"Missing required contract text: {missing}")

print("Skill contract checks passed.")
PY
```

On Windows PowerShell, if shell redirection is awkward, run the same Python snippet from a temporary script.

## Release Checklist

For maintainers preparing a release:

1. Update `version` in `skills/storm/SKILL.md`.
2. Run validation.
3. Commit with a clear English message.
4. Create a matching Git tag, for example `v0.2.1`.
5. Push only after explicitly deciding to publish.
6. Create a GitHub Release for the tag and mark it as latest when appropriate.

## Pull Requests

Good pull requests usually include:

- A short explanation of the behavior change.
- The affected files.
- Validation commands and results.
- Any known limitations or follow-up work.

Please avoid committing generated `.results/` artifacts, local caches, secrets, or machine-specific files.

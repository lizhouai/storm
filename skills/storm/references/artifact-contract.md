# Artifact And Citation Contract

## Public Artifacts

Normal non-interactive research publishes exactly these four files under the
resolved output directory:

1. `direct_gen_outline.html`
2. `storm_gen_outline.html`
3. `storm_gen_article.html`
4. `storm_gen_article_polished.html`

The guarded publication path supports HTML only and defaults to
`.results/<topic-slug>/`. If the user requests another Classic file format,
offer the validated HTML bundle or chat-only fallback and disclose that the
non-HTML output would not pass the guarded artifact gate. Internal state, event
logs, retrieval traces, information tables, and audits belong in `.storm-run/`
and do not count as additional public deliverables.

## Structural Gates

- Every public file is non-empty, strict UTF-8, and free of replacement or
  known mojibake markers.
- HTML includes `<meta charset="utf-8">`, a meaningful title, balanced basic
  document structure, and no executable retrieved script or unsafe URL scheme.
- Outlines use valid `h1` through `h3` progression and do not duplicate the
  topic or add a References section.
- Articles contain no obvious truncation marker and the polished article has a
  reference list.

## Citation Gates

- Citation ids are positive, unique in the source registry, consecutive after
  polishing, and actually used.
- Every used citation maps to exactly one source; every listed source is used or
  explicitly recorded as unused evidence.
- Each factual claim records citation ids, source ids, support status, evidence
  note, and action. Semantic support may be judged by an Agent, but the judgment
  and evidence must be persisted for audit.
- Missing source mappings, duplicate ids, out-of-range ids, unsupported claims,
  or dangling references fail closed.

## Staging And Publication

Never silently overwrite existing output. Resolve a new run-specific sibling or
obtain explicit current authorization. Write into a same-filesystem staging
directory at `.storm-run/staging`, close files, validate the complete set,
calculate SHA-256 hashes,
then advance the guarded lifecycle. The Classic `completed` transition performs
a same-filesystem temporary-file plus `os.replace` publication for every
validated artifact and atomically writes `.storm-run/publication.json` with the
published SHA-256 values. COMPLETE runs fail validation if that receipt is
missing or disagrees with run state. A failure leaves the last valid public
output untouched and reports any retained staging path.

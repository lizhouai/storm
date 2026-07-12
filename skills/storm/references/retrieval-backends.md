# Optional Retrieval Backends

Load this reference when guarded research needs evidence retrieval. Infer the
mechanism from the user's available inputs: ordinary Agent-led research uses
host-ranked results, a user-provided local corpus uses deterministic lexical
search, and an explicitly configured provider/model/version uses embedding
retrieval. Users do not need to know or name these implementation mechanisms.
A retrieval backend chooses evidence; it is separate from `execution_backend`,
which still records `guarded-agent`, `prompt-only`, or `local-runner`.

## Backend Contract

The bundled `../scripts/retrieval_backend.py` exposes the same two operations
for all backends:

```text
index  --backend host|lexical|embedding --corpus <jsonl> --output <index.json>
search --index <index.json> --query <text> --top-k <n>
```

Corpus JSONL rows require `source_id` and `text`; `title` and `url` are
optional. Keep indexes and result-row traces internal, normally at
`.storm-run/retrieval-index.json` and `.storm-run/retrieval-log.jsonl`. Each
trace hit records the requested and effective backend, versioned algorithm,
model/provider version when applicable, query, top-k, chunk parameters, rank,
score, source/chunk ids, exact snippet, and its SHA-256 hash. The existing
interview and information-table gates continue to resolve `source_id` from
these richer rows.

### Host

Host retrieval preserves the current Agent or runner's semantic ranking. The
script never invokes a host search or network implicitly: pass the already
ranked result rows with `search --host-results <jsonl>`. This makes the ranking
and scores auditable without pretending the bundled script selected them.
When one source has multiple chunks, each host result must include `chunk_id`;
the adapter never guesses which snippet the host selected.

### Lexical

Lexical retrieval is the zero-dependency deterministic fallback. It uses
versioned BM25 scoring, NFKC/case folding, ASCII word terms, and Unicode
character/bigram terms for CJK and other non-ASCII writing systems. Chunk sizes
are Unicode code points, not model tokens. Equal scores sort by source id and
chunk id so repeated runs over the same corpus are stable.

### Embedding

Embedding retrieval is optional and never installs or discovers a model. It
requires an explicit trusted provider, model name, and provider version:

```text
index --backend embedding --embedding-provider <module-or-path>:<callable> \
  --model <name> --provider-version <version> ...
search --index <index.json> --embedding-provider <module-or-path>:<callable> ...
```

The callable receives `texts: list[str]` and keyword argument `model`, then
returns one finite, non-zero numeric vector per text. Provider code executes in
the current Python process, so use only a provider already trusted and
authorized by the current user. Do not log provider credentials or source
bodies outside the selected output boundary.

## Failure And Fallback

Invalid corpora, blank queries, malformed vectors, dimension mismatches, bad
hashes, missing host results, and unavailable providers fail closed. Embedding
unavailability is an error by default. Only an explicit `--fallback lexical`
may downgrade it; index/search output and every trace row expose the requested
backend, effective backend, and fallback reason. Never fall back to host
retrieval because doing so could silently widen the source or network boundary.
Malformed or non-finite provider output never qualifies for fallback.

Index and JSON report outputs refuse to overwrite an existing path. Use
`index --replace` or `search --replace-output` only after the current user has
authorized replacement. Trace writes append atomically by default; replacing a
trace additionally requires `--replace-trace`.

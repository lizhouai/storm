# Experimental Retrieval Backends

Status: **Experimental**. These retrieval paths are in testing and are selected
automatically for guarded evidence retrieval. They must fail closed when their
documented contracts cannot be satisfied.

Load this reference when guarded research needs evidence retrieval. Infer the
mechanism from the user's available inputs: ordinary Agent-led research uses
host-ranked results, while a user-provided local corpus uses deterministic
lexical search. Users do not need to know or name these implementation
mechanisms.
A retrieval backend chooses evidence; it is separate from `execution_backend`,
which still records `guarded-agent`, `prompt-only`, or `local-runner`.

## Backend Contract

The bundled `../scripts/retrieval_backend.py` exposes the same two operations
for all backends:

```text
index  --backend host|lexical --corpus <jsonl> --output <index.json>
search --index <index.json> --query <text> --top-k <n>
```

Corpus JSONL rows require `source_id` and `text`; `title` and `url` are
optional. Keep indexes and result-row traces internal, normally at
`.storm-run/retrieval-index.json` and `.storm-run/retrieval-log.jsonl`. Each
trace hit records the requested and effective backend, versioned algorithm,
backend identity, query, top-k, chunk parameters, rank, score, source/chunk ids,
exact snippet, and its SHA-256 hash. The existing
interview and information-table gates continue to resolve `source_id` from
these richer rows.

### Host

Host retrieval preserves the current Agent or runner's semantic ranking. The
script never invokes a host search or network implicitly: pass the already
ranked result rows with `search --host-results <jsonl>`. This makes the ranking
and scores auditable without pretending the bundled script selected them.
When one source has multiple chunks, each host result must include `chunk_id`;
the adapter never guesses which snippet the host selected.

Each host-results JSONL row requires a resolvable `source_id` and finite numeric
`score`; `chunk_id` is optional only when that source has one indexed chunk:

```json
{"source_id":"S1","chunk_id":"S1#0001","score":0.92}
```

Persist the promised trace explicitly:

```text
python scripts/retrieval_backend.py index --backend host \
  --corpus <corpus.jsonl> --output <run>/.storm-run/retrieval-index.json
python scripts/retrieval_backend.py search \
  --index <run>/.storm-run/retrieval-index.json --query <text> --top-k <n> \
  --host-results <ranked-results.jsonl> \
  --trace <run>/.storm-run/retrieval-log.jsonl
```

### Lexical

Lexical retrieval is the zero-dependency deterministic corpus path. It uses
versioned BM25 scoring, NFKC/case folding, ASCII word terms, and Unicode
character/bigram terms for CJK and other non-ASCII writing systems. Chunk sizes
are Unicode code points, not model tokens. Equal scores sort by source id and
chunk id so repeated runs over the same corpus are stable.

## Failure And Fallback

Invalid corpora, blank queries, bad hashes, missing host results, and
inconsistent index metadata fail closed.
There is no implicit cross-backend fallback: switching from host to lexical or
from lexical to host requires an explicit new command so the source boundary
cannot widen silently. The bundled runtime never installs packages, imports
provider code, or contacts a model or search service.

Index and JSON report outputs refuse to overwrite an existing path. Use
`index --replace` or `search --replace-output` only after the current user has
authorized replacement. Trace writes append atomically by default; replacing a
trace additionally requires `--replace-trace`.

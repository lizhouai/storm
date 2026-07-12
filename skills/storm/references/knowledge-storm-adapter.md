# Experimental Official Knowledge STORM Adapter

Status: **Experimental**. This import path is in testing, remains optional, and
must fail closed when the supported upstream contract cannot be verified.

Load this reference when the user provides an output directory from an already
executed official Classic STORM run or asks to import or synchronize that run
into the guarded workflow. Infer this from the described source and goal; do
not require an adapter name or implementation-stage label. The bundle includes
an import adapter, not
`knowledge-storm`, DSPy, models, retrievers, credentials, or an executable
Co-STORM runtime. The supported stable contract is
`knowledge-storm>=1.1.1,<1.2`, currently verified against official 1.1.1.
Version discovery uses distribution metadata because the upstream module
version may not match the installed distribution.

Primary upstream contracts:

- [Official API and configuration](https://github.com/stanford-oval/storm#api)
- [Classic runner lifecycle and output files](https://github.com/stanford-oval/storm/blob/main/knowledge_storm/storm_wiki/engine.py)
- [Conversation and article data structures](https://github.com/stanford-oval/storm/blob/main/knowledge_storm/storm_wiki/modules/storm_dataclass.py)
- [Article polishing behavior](https://github.com/stanford-oval/storm/blob/main/knowledge_storm/storm_wiki/modules/article_polish.py)
- [Published distribution metadata](https://pypi.org/project/knowledge-storm/)

## Probe Without Import

Use the bundled adapter before attempting execution:

```text
python scripts/runner_adapter.py probe
```

The probe uses `importlib.util.find_spec` and
`importlib.metadata.version("knowledge-storm")`; it does not import the
`knowledge_storm` root package or install anything. A missing or unsupported
dependency is a requirement report, not permission to install it.

## Safe Upstream Execution

Run the official runner only when the current user has authorized its existing
environment, credentials, network access, and source boundary. Give it a fresh
private output directory, never the guarded public output directory: upstream
uses overwrite-style writes for topic files. The private runner directory must
not be the guarded output's ancestor or descendant; any tree overlap is
rejected so raw configuration and LM history cannot enter the public boundary.

The supported `>=1.1.1,<1.2` Classic runner can emit:

```text
conversation_log.json
raw_search_results.json
direct_gen_outline.txt
storm_gen_outline.txt
storm_gen_article.txt
url_to_info.json
storm_gen_article_polished.txt
run_config.json
llm_call_history.jsonl
```

`run_config.json` and `llm_call_history.jsonl` require an explicit upstream
`post_run()` call. Treat both as untrusted and potentially sensitive.

### Capture The Polished Reference Map

Do not reuse draft `url_to_info.json` for the polished article. Upstream
polishing may reorder or remove citations without writing its updated reference
map. A reliable wrapper must:

1. run research/outline/draft with `do_polish_article=False`;
2. reconstruct the draft `StormArticle` from its text and references;
3. call `runner.run_article_polishing_module(...)` and retain the returned
   polished article object;
4. call that object's `dump_reference_to_file(...)` as
   `polished_url_to_info.json` in the private runner directory;
5. call `runner.post_run()`.

If `polished_url_to_info.json` is absent or inconsistent, the adapter refuses
the polish phase. It never guesses that draft and polished citation ids match.
The polished map may retain metadata for citations removed during polishing;
`url_to_unified_index` keys must be a subset of `url_to_info` keys, and only
the indexed sources are imported.

## Phase-By-Phase Import

Initialize a guarded Classic run with `execution_backend=local-runner`, then
call:

```text
python scripts/runner_adapter.py sync \
  --run <output>/.storm-run/run.json \
  --source <private-official-topic-directory> \
  --runner-version 1.1.1 \
  --retriever <name> --retriever-version <version> --search-top-k <n>
```

Each `sync` reads the guarded `next_action`, writes only that phase's evidence,
and returns the single suggested state event. It never edits `run.json`, appends
the state event log, advances a phase, installs a package, executes the runner,
or publishes files.

| Guarded next action | Imported evidence |
|---|---|
| `define_scope` | redacted `runner-manifest.json`, input hashes, runner/retriever identity, LM-history count/hash |
| `generate_perspectives` | `perspectives.json` from the conversation log |
| `run_interviews` | filtered-query `interviews.jsonl` and source-resolvable `retrieval-log.jsonl` |
| `build_information_table` | deduplicated `information-table.jsonl` |
| outline actions | escaped standalone staging HTML from the two outline files |
| `write_draft` | escaped draft HTML and internal draft source mapping |
| `polish_article` | escaped polished HTML, authoritative polished sources, and unreviewed claim candidates |
| `verify_artifacts` | no automatic event; requires semantic claim review, citation audit, and artifact validation |
| `publish` | no direct write; instructs the guarded state CLI to perform hash-checked, retry-safe publication |

Blank queries are filtered, but a turn with no remaining query or resolvable
source fails closed. Raw runner HTML is escaped, unsafe URLs are rendered as
plain text, strict UTF-8 is required, and conflicting adapter outputs are never
overwritten. Same-content retries are idempotent.

Claim candidates contain the actual cited paragraph with citation markers
removed, not a generic placeholder. They remain `unreviewed`; a reviewer must
compare each persisted factual claim against its mapped source before changing
the support decision.

The manifest allowlists non-secret model fields, records explicitly supplied
retriever settings, and stores only the line count and SHA-256 of LM history.
It never copies prompts, responses, API keys, tokens, endpoints, or raw runner
configuration. Workflow state and inputs are traceable; generated text is not
claimed reproducible.

## Capability Boundary

This adapter supports the Classic `STORMWikiRunner` file tree only. Official
`CoStormRunner` uses a different interactive API and does not emit the Classic
four-artifact tree, so route it separately and do not present this adapter as a
Co-STORM runtime. A runner exit code, adapter sync, or candidate claim file is
never sufficient to claim guarded completion.

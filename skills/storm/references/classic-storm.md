# Classic STORM

Use this reference for non-interactive research, corpus-restricted research,
and the explicit chat-only exception.

## Algorithm

1. Frame topic, audience, scope, recency, language, source limits, and depth.
2. Plan sources before retrieval. Prefer primary papers, standards, official
   documentation, and strong surveys; use vendor material only for claims about
   that vendor.
3. Generate `Basic fact writer` and up to three non-overlapping perspectives.
4. For each perspective, run up to three interview turns. Ask one new question,
   produce at most three non-empty queries, retrieve, and answer only from the
   gathered evidence.
5. Build an information table containing perspective, question, query, source
   id, URL or local id, title, date, snippet, supported claim, and reliability
   note. Deduplicate by source and claim.
6. Generate the direct outline from the topic alone, then refine it from the
   interview evidence. Use only `#`, `##`, and `###`; exclude a duplicate topic
   heading and a References heading from outline artifacts.
7. Write sections only from section-relevant evidence and cite factual claims
   with temporary source ids.
8. Polish, remove duplication, reorder citations by first appearance, build the
   numbered reference list, and record unsupported or stale evidence gaps.
9. Apply `artifact-contract.md` before publication.

## Chat-Only Exception

Only when the user explicitly asks for a quick answer, chat only, or no files,
return a compact brief with scope, perspectives, question/query log, refined
outline, cited synthesis, numbered references, and verification notes. Do not
silently substitute this exception for normal Artifact STORM.

## Phase Evidence

Each phase must preserve enough evidence for the next phase to be checked:

- perspectives: stable unique role ids, including Basic fact writer;
- interviews: non-empty queries and resolvable source ids;
- information table: claim-to-snippet-to-source mapping;
- outlines: valid heading hierarchy and evidence trace for the refined form;
- draft: every top-level section completed and every citation resolvable;
- polished article: citations renumbered without gaps or dangling references.

Prompt-only execution describes these gates but cannot mechanically enforce
them. A guarded runtime must refuse advancement when phase evidence is absent.

# Prompt-native Co-STORM example: RAG evaluation roundtable

This is a compact, curated transcript generated with the prompt-native Co-STORM preview contract. The participants below are visibly labeled simulated roles, not independently running agents or the upstream `CoStormRunner`.

## Prompt

```text
Use the prompt-native Co-STORM preview to explore how an engineering team should evaluate a RAG system. Start with a roundtable, maintain a cited mind map, and let me steer.
```

## Warm start

**Basic fact writer**

The original RAG architecture combines a parametric generator with retrieved non-parametric memory. Evaluation therefore needs to observe both the retrieval path and the generated answer, rather than treating the system as one opaque model.[1]

**Evaluation scientist**

RAGAs separates relevant retrieval, faithful use of context, and generation quality, and proposes metrics that do not require human ground truth for every sample. That makes it useful for frequent evaluation loops, but the paper's automation goal does not remove the need to validate metric behavior in the target domain.[2]

**Systems diagnostician**

RAGChecker explicitly evaluates retrieval and generation modules with fine-grained diagnostic metrics. Its purpose is not only to rank systems, but to reveal architecture trade-offs and likely failure locations.[4]

**Moderator**

The first decision is whether the team needs fast regression feedback, calibrated comparison, or failure diagnosis. ARES adds a distinct path: trained lightweight judges combined with a small human-annotated set through prediction-powered inference.[3]

### Initial mind map

```text
RAG evaluation
├── System boundary
│   ├── Retrieval
│   └── Generation
├── Quality dimensions
│   ├── Context relevance [2][3]
│   ├── Answer faithfulness [2][3]
│   └── Answer relevance [3]
└── Evaluation intent
    ├── Fast multidimensional feedback → RAGAs [2]
    ├── Calibrated system comparison → ARES [3]
    └── Fine-grained diagnosis → RAGChecker [4]
```

### Choice-first steering

- **Diagnose failures — recommended:** trace a bad answer back to retrieval or generation behavior.
- **Compare automation assumptions:** examine reference-free metrics versus trained judges and labeled calibration.
- **Design a minimal stack:** combine routine checks, escalation, and human review.

These options are suggestions, not a closed menu; any free-form question,
constraint, redirection, or request to conclude is valid steering.

## User steering

```text
Diagnose failures. Show me how the roles disagree about what to measure first.
```

## Steered turn

**Systems diagnostician — Primary speaker**

Start with component evidence. RAGChecker's retrieval and generation metrics are designed to reveal patterns that an end-to-end answer score can hide.[4] If retrieved context is irrelevant, generation faithfulness alone cannot repair the pipeline; if retrieval is adequate, the investigation moves to context use and answer construction.

**Evaluation scientist — Response**

Component detail is useful, but a diagnostic metric is still a measurement model. ARES addresses judge error by pairing trained lightweight judges with a small human-annotated set and prediction-powered inference.[3] The disagreement is therefore not “diagnostics or calibration”; it is how much calibration a diagnostic decision requires.

**Moderator**

The mind map now contains two linked questions: where did the failure occur, and how trustworthy is the metric that says so? The next move should connect them in a layered evaluation stack rather than select one framework as universally best.

### Mind-map delta

```text
Evaluation intent
└── Fine-grained diagnosis
    ├── Locate retrieval failure [4]
    ├── Locate generation failure [4]
    └── Validate diagnostic judgments
        ├── Human-annotated calibration set [3]
        └── Domain-transfer check [3]
```

### Open questions

- Which production failures are consequential enough to require human adjudication?
- Does the team's evaluation set contain the domain shifts seen in deployment?
- Which metrics are stable enough for a blocking regression gate?

### Next steering choice

- **Build the layered stack — recommended:** turn the map into a practical regression and escalation workflow.
- **Challenge judge reliability:** focus on model-based metric failure modes.
- **Write the report:** conclude from the current cited mind map.

The same free-form steering rule applies after every round.

## References

1. Lewis et al., [Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](https://papers.neurips.cc/paper/2020/hash/6b493230205f780e1bc26945df7481e5-Abstract.html), NeurIPS 2020.
2. Es et al., [RAGAs: Automated Evaluation of Retrieval Augmented Generation](https://aclanthology.org/2024.eacl-demo.16/), EACL 2024.
3. Saad-Falcon et al., [ARES: An Automated Evaluation Framework for Retrieval-Augmented Generation Systems](https://aclanthology.org/2024.naacl-long.20/), NAACL 2024.
4. Ru et al., [RAGChecker: A Fine-grained Framework for Diagnosing Retrieval-Augmented Generation](https://proceedings.neurips.cc/paper_files/paper/2024/hash/27245589131d17368cccdfa990cbf16e-Abstract-Datasets_and_Benchmarks_Track.html), NeurIPS 2024.

## What this example demonstrates

- Every visible role makes a distinct, cited contribution.
- The user-selected branch determines the next primary speaker.
- The respondent challenges the primary speaker instead of paraphrasing it.
- The moderator connects unused evidence to the next research decision.
- The mind map records a cited delta and unresolved questions.
- This curated transcript did not exercise the optional durable `record-turn`
  path, and no upstream Co-STORM parity is claimed.

For a longer run that reaches explicit file output and a final report, see the
[RAG technology research example](../co-storm-rag-technology/README.md).

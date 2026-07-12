# Changelog

All notable changes to the STORM Research Skill are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Releases are identified by `vX.Y.Z` Git tags.

## [Unreleased]

### Changed

- Made `CONTRIBUTING.md` the single source of truth for local development,
  validation, changelog, and release instructions, and reduced the README to a
  concise contribution link.

## [0.5.0] - 2026-07-12

### Added

- Added experimental guarded retrieval routing for Agent-ranked evidence,
  local lexical corpora, and explicitly configured embedding providers.
- Added an experimental zero-dependency adapter that imports compatible
  completed official Classic STORM output into the guarded artifact lifecycle
  without installing or executing the upstream runner.
- Added deterministic retrieval traces, corpus-boundary enforcement, stable
  `knowledge-storm` output fixtures, and regression coverage for both features.

### Changed

- Routed capabilities from the user's requested outcome and available inputs,
  without exposing internal backend or adapter labels as required user terms.
- Clarified that Co-STORM steering suggestions are optional and that users can
  provide free-form direction at every non-final turn.
- Marked retrieval routing and official Classic output import as experimental
  across the skill contract, OpenAI metadata, README, references, and examples.
- Expanded release validation to 87 unit tests while retaining the 120-run
  isolated offline contract canary with zero illegal transitions.

## [0.4.1] - 2026-07-11

### Added

- Added versioned validation for persistent Co-STORM turns, including stable
  participant and source mappings, idempotent hash-linked logs, and lifecycle
  gates for warm start and final reporting.
- Added publication receipts and post-publication SHA-256 verification for the
  four Classic STORM artifacts.

### Changed

- Hardened Classic completion with staging-first publication, strict citation
  and artifact evidence, and rollback for recoverable publication failures.
- Synchronized documentation, examples, CI, forward-eval fixtures, and
  installed-bundle checks with the guarded runtime contract.

## [0.4.0] - 2026-07-11

### Added

- Added the zero-dependency guarded runtime with versioned state, legal phase
  transitions, atomic checkpoints, recovery, event hashes, and explicit
  completion state.
- Added structural artifact validation, citation auditing, and an executable
  12-case offline forward-eval contract.
- Added focused Classic, Co-STORM, Local Runner, artifact, safety, and state
  references while retaining the compatibility index.
- Added the end-to-end Co-STORM report example and repository social preview.

### Changed

- Made guarded execution the default for file-producing Classic and Local
  Runner requests when Python is available.
- Renamed the public repository to `lizhouai/storm-research-skill` and updated
  the install path, documentation, examples, CI, and Pages URLs.

## [0.3.0] - 2026-07-10

### Added

- Added the prompt-native Co-STORM preview with visible role-attributed turns,
  choice-first steering, cited mind-map updates, moderator cadence, checkpoints,
  and recovery guidance.
- Added safety boundaries for untrusted sources, local runners, output
  conflicts, remote side effects, and checkpoint reloads.
- Added evaluation fixtures, dependency-free validation, regression tests, and
  GitHub Actions coverage for pinned and latest skills CLI behavior.

### Changed

- Clarified install and update scope, cross-agent compatibility, and the
  boundary between this prompt-native preview and the upstream Co-STORM engine.

## [0.2.1] - 2026-07-09

### Added

- Added the contribution guide.
- Added README badges for release and license metadata.

### Changed

- Clarified that Co-STORM-style workflows were still in development and
  removed duplicated artifact wording from the README.

## [0.2.0] - 2026-07-09

### Added

- Moved the skill into the standard installable `skills/storm/` bundle layout.

### Changed

- Made non-interactive STORM research produce the standard four artifact files
  by default.
- Defaulted an unspecified format to HTML and an unspecified destination to
  `.results/<topic-slug>/`.
- Added UTF-8 and Windows file-hygiene guidance for generated artifacts.

## [0.1.0] - 2026-07-09

### Added

- Published the initial `SKILL.md`-based STORM Research Skill with Classic
  research and Co-STORM-style interactive workflows.
- Added upstream attribution, the public installation path, and the MIT
  License.

[Unreleased]: https://github.com/lizhouai/storm-research-skill/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/lizhouai/storm-research-skill/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/lizhouai/storm-research-skill/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/lizhouai/storm-research-skill/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/lizhouai/storm-research-skill/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/lizhouai/storm-research-skill/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/lizhouai/storm-research-skill/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/lizhouai/storm-research-skill/releases/tag/v0.1.0

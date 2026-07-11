# STORM Method Compatibility Index

The STORM method is split into mode-specific references so an Agent loads only
the procedure required by the selected route. Existing callers may continue to
open this file, but should then follow only the relevant links:

- Classic research and chat brief: `classic-storm.md`
- Prompt-native Co-STORM preview: `co-storm.md`
- Existing local runner execution: `local-runner.md`
- Four public files, staging, HTML, UTF-8, and citation gates: `artifact-contract.md`
- Retrieval, checkpoint, runner, and side-effect safety: `safety-contract.md`
- Versioned guarded run state: `run-state.schema.json`

The public entry point remains `../SKILL.md`. This compatibility index does not
define a second mode or installation target.

Migration rule: do not delete this file until installed-bundle smoke tests and
forward evals prove that all supported Agent surfaces resolve the split
references. The prompt-native preview still simulates visible participants and
does not bundle independently running expert agents or an executable
`CoStormRunner`.

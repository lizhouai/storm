# Local Runner STORM

Use this route only when the user asks to execute an existing repository,
script, environment, or installed STORM implementation.

1. Inspect the runner interface, expected environment, flags, topic handling,
   output directory, and resume behavior before execution.
2. Preserve the exact display topic; use a separate filesystem-safe slug.
3. Use the provided runtime and least required permissions. Do not install
   dependencies, edit source, expose secrets, upload data, or perform remote
   writes unless the current user explicitly authorizes that action.
4. Filter blank generated queries. On a transient remote reset, reduce
   concurrency and retry once before reporting the blocker.
5. Capture runner version, configuration, command, exit status, artifact paths,
   and available conversation or retrieval logs.
6. Map runner outputs into the standard four public artifact names when
   possible. If the runner writes text and no format was requested, convert the
   four artifacts to standalone UTF-8 HTML.
7. Apply `artifact-contract.md` and `safety-contract.md`. Runner success does
   not bypass citation, encoding, HTML, overwrite, or publication gates.

If the user asks for an official Co-STORM implementation, use this route and
verify that implementation rather than presenting the prompt-native preview as
an executable runtime.

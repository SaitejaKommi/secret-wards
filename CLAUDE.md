# Secret Wards (DevForge Track 3)

Offline, LLM-free de-identification and record linkage for messy English / Hindi / Hinglish hospital records.

## Read before any work
Docs live on the `docs` branch, checked out as a git worktree at `docs-wt/`.
1. `docs-wt/PROBLEM_ORIGINAL.md` (source of truth, never edit)
2. `docs-wt/PROBLEM_STATEMENT.md`
3. `docs-wt/ARCHITECTURE.md`
4. `docs-wt/PROGRESS.md`

If `docs-wt/` is missing: `git worktree add docs-wt docs`

## Non-negotiables
- No LLMs or generative models in the pipeline; no pretrained transformer above 50M parameters.
- CPU only, no network calls at run time.
- Deterministic: same input, config and keys give the same output.
- No PII in outputs, logs, temp files, exception messages, reports, tests or docs. Synthetic data only.
- No hardcoding to our own synthetic names or templates.
- Fail closed: if a file cannot be processed safely, quarantine it.

## Working rules
- Stages talk only through the types in `contracts.py`. Ask before changing them.
- Small commits with honest messages. Never rewrite or fake history.
- Every detection or linkage change: run the scorer and record the numbers.
- After each milestone, update `docs-wt/PROGRESS.md` and commit it on `docs`.
- Explain new modules briefly so the team can answer judges' questions.
- If a design choice is unclear or a bug survives two attempts, stop and ask. Suggest switching to Opus (`/model opus`).

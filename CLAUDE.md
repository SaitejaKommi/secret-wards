# Secret Wards (DevForge Track 3)

Offline, LLM-free de-identification and record linkage for messy English / Hindi / Hinglish hospital records.

## Read before any work
Docs live on the `docs` branch, checked out as a git worktree at `docs-wt/`.
1. `docs-wt/TOOLKIT.md` (READ FIRST: the official organiser kit, the exact output contract `raksha.toml` / `main.py` / `RAKSHA_SECRET` / `sanitized/` / `report.json` / `records.jsonl`, scoring, penalties, and every conflict with our code. Where it differs from older docs, the kit wins.)
2. `docs-wt/PROBLEM_ORIGINAL.md` (original statement, never edit; superseded by `docs-wt/toolkit/docs/PROBLEM_STATEMENT.md` for contract questions)
3. `docs-wt/PROBLEM_STATEMENT.md`
4. `docs-wt/ARCHITECTURE.md`
5. `docs-wt/PROGRESS.md` and `docs-wt/FRIEND_TASKS.md` (who owns which files, git workflow)

If `docs-wt/` is missing: `git worktree add docs-wt docs`
The official kit itself is cloned NEXT TO this repo, never inside it: `git clone https://github.com/Reinforce-SST/Secret-Wards-ToolKit.git`

## Non-negotiables
- No LLMs or generative models in the pipeline; no pretrained transformer above 50M parameters.
- CPU only, no network calls at run time.
- Deterministic: same input, config and keys (the secret in `RAKSHA_SECRET`) give the same output.
- No PII in outputs, logs, temp files, exception messages, reports, tests or docs. Synthetic data only. Never write `RAKSHA_SECRET` anywhere.
- No hardcoding to our own synthetic names or templates, and NEVER to names, numbers or values from the practice data or its answer key.
- Never commit the kit's `dev/` folder (practice input, truth, attacker), `keys/`, `*.key`, `data/`, `out/`, `.venv/`.
- Fail closed: if a file cannot be processed safely, quarantine the whole file. Never drop records silently and never copy a file raw.

## Working rules
- Stages talk only through the types in `contracts.py`. Ask before changing them.
- Small commits with honest messages. Never rewrite or fake history. Work on your own branch and open a pull request into `main` (see `docs-wt/FRIEND_TASKS.md`).
- Every detection or linkage change: run the scorer (and, once the contract adapter exists, the kit's `validate_output.py` and `check_dev.py`) and record the numbers.
- After each milestone, update `docs-wt/PROGRESS.md` and commit it on `docs`.
- Explain new modules briefly so the team can answer judges' questions.
- If a design choice is unclear or a bug survives two attempts, stop and ask. Suggest switching to Opus (`/model opus`).

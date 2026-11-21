# Session handoff (2026-11-21, updated after Gate A)

Read this first when continuing the Ferlance work in a new session.

## Where things stand

- **Session 1 (migration) is done and merged.** The frontend is ported to React 19 + TypeScript + Vite with exact parity. PR #12 was merged into `main` on 2026-11-21 and is tagged `v1.0.0`.
  - The PR description lists the verification evidence, intentional deviations, known follow-ups and the payload size.
  - The architecture is described in `docs/ARCHITECTURE.md` (Frontend section) and in `README.md`.
- **Session 2 (updates) is in progress.** Gate A (setup) is on branch `docs/gate-a-setup`. That branch merges `chore/update-phase-handoff` (this handoff and `tools/verify/`) and adds:
  - `docs/SKILLS_AUDIT.md`
  - `docs/PERSONAS.md`
  - `docs/PRD.md`, which replaces `docs/UPDATE_PLAN.md` and keeps the brief verbatim as an appendix
  - `CHANGELOG.md`

## How the owner wants to work

- They expect a senior engineer standard: transparent, verified work with good code quality.
- Ask only when you're blocked on a real decision. Otherwise recommend and proceed. The owner rejected two clarifying-question dialogs and pointed to the update brief (now the appendix of `docs/PRD.md`) as the source of answers.
- Use feature branches and PRs into `main`, never commits to `main`. Write clear commit messages.
- Before each feature is handed over, it must pass `/code-review` and be verified (see the per-change gate below).
- Ask for credentials (AWS, OCR provider, Expo/EAS) only at the step that needs them.
- Flag up front anything that could degrade experience, performance, cost or delivery. The brief asks for this explicitly.
- Model plan: a strong model (Opus) leads architecture, shared code, review and sign-off. Cheaper agents (Sonnet) take self-contained ports or features against a written contract (see `tools/verify/PORTING.md` for the pattern). Keep fan-out under about 10 agents per chunk.

## Session 2 plan (agreed order)

### Gate A — setup
1. **Done.** Skill audit in `docs/SKILLS_AUDIT.md`. `/skill-doctor` is not exposed to the agent, so the audit was done by hand. Nothing is installed locally. Disabling account-level skills and connectors is waiting on the owner. `/loop` is available.
2. **Done.** Personas in `docs/PERSONAS.md`, from cited web research. `anthropic-skills:deep-research` *is* available, but it fans out subagents and costs several times more, so it is saved for the #8 and #3 decisions. Write 3–5 Ghanaian SME personas, for example:
   - a market trader on MoMo
   - a pharmacy owner with stock
   - a services firm with an accountant
   - a growing retailer on Excel

   For each, cover devices, connectivity, literacy, tools, pain points and success criteria.
3. **Done.** Restructure `docs/UPDATE_PLAN.md` into `docs/PRD.md`: goals, per-feature requirements, non-goals, risks and acceptance criteria. Adopt SemVer (v1.0.0 = the React migration), add `CHANGELOG.md` in Keep a Changelog format, and tag releases.

### Gate B — features
The requirements and acceptance criteria for each feature are in `docs/PRD.md` §5. Migration follow-ups are F0 (v1.0.x) and come first.

Each feature gets its own `feat/*` branch off `main`. Planned order:
1. Interface refinement and design system (#7), then analytics visuals (#6): circular, animated and responsive, respecting `prefers-reduced-motion`.
2. Onboarding flow and admin console (#4/#5). Admin endpoints already exist in `backend/routers/admin.py`, and there is an admin card in Settings.
3. OCR inventory capture and inventory↔product sync (#1/#2).
4. RAG improvement (#8). Try sqlite-vec next to the existing FTS5 before adding a vector DB.
5. Data lake (#3). It is likely overkill at the current scale. Propose a scheduled Parquet export to S3 first.
6. Expo mobile app (#9). Share the TS API types from `frontend/src/lib/types.ts`.

### Per-change gate
1. Run `/loop` asking "Does the app provide ease, comfort and value to the Ghanaian SME?" against each persona.
2. Verify (stand-in for `/verify`): `npm --prefix frontend run check`, `npm --prefix frontend run build`, `.venv/bin/pytest -q`, and a browser check in both themes at phone width (`tools/verify`).
3. Run `/code-review` with fixes.
4. Open a PR.
5. Add a CHANGELOG entry and bump the version.

## Known follow-ups from the migration (all listed in PR #12)
- ~~First-load size, the stale date window after a file switch, and the Product name Z→A sort~~ were fixed in v1.0.1 (PRD F0.1–F0.3). Going below about 108 KB on the wire needs Preact, which is the owner's decision (PRD §8).
- ~~Open PRs #10 and #11 need rebasing.~~ That note was stale: both were merged before #12, and the folder-import feature from #11 survived the migration (`backend/routers/datasets.py`, `frontend/src/app/views/Data.tsx`).
- A real AI provider was never exercised; only a mock LLM was used. Brave was removed (owner has no key): outside context is now the Ghana calendar plus free GDELT news.

## Verification tooling (`tools/verify/`)
These are dev-only scripts. They need Playwright: `npm i playwright pngjs pixelmatch` in a scratch dir, then `npx playwright install chromium`.

| Script | What it does |
|---|---|
| `serve.sh <port> <datadir>` | Runs the backend on a throwaway data dir. |
| `seed.py <base-url> [bad.csv]` | Seeds the demo account `demo@ferlance.test` / `demo-pass-123` with 4 months of sales, MoMo, inventory and balances. |
| `shots.mjs <base> <out>` | Screenshots every page in light/dark and desktop/phone. |
| `states.mjs <base> <out>` | Screenshots extra data states. It needs `fresh@ferlance.test` and `costs@ferlance.test`, seeded as described in PR #12. |
| `diff.mjs <dirA> <dirB> <diffOut>` | Pixel diff between two screenshot dirs. |
| `e2e.mjs` / `e2e2.mjs <base>` | End-to-end flows. Use them with `mockllm.py <port> [delaySeconds]` and the env vars in their headers. `e2e.mjs` needs `FERLANCE_ACCESS_TOKEN_SECONDS=4`. `e2e2.mjs` needs `FERLANCE_ADMIN_EMAILS=demo@ferlance.test` and a 32+ character `FERLANCE_SECRET_KEY`. Both need `OPENROUTER_KEY`, `OPENROUTER_URL` and `OPENROUTER_MODELS` pointing at the mock. |
| `PORTING.md` | The contract given to the porting agents. It is a template for briefing feature agents. |

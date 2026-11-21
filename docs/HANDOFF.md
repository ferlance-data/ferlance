# Session handoff (2026-11-21)

Read this first when continuing the Ferlance work in a new session.

## Where things stand

- **Session 1 (migration) is done.** The frontend is ported to React 19 + TypeScript + Vite with exact parity. It is on branch `feat/react-migration`, in **PR #12 → `main`**, waiting for the owner's review and merge.
  - The PR description lists the verification evidence, intentional deviations, known follow-ups and the payload size.
  - The architecture is described in `docs/ARCHITECTURE.md` (Frontend section) and in `README.md`.
- **Session 2 (updates) has not started.** It is gated on PR #12 merging.
- This branch (`chore/update-phase-handoff`, based on `feat/react-migration`) holds:
  - `docs/UPDATE_PLAN.md`, the owner's update brief
  - this handoff
  - `tools/verify/`, the parity and e2e tooling used to verify the migration

## How the owner wants to work

- They expect a senior engineer standard: transparent, verified work with good code quality.
- Ask only when you're blocked on a real decision. Otherwise recommend and proceed. The owner rejected two clarifying-question dialogs and pointed to `UPDATE_PLAN.md` as the source of answers.
- Use feature branches and PRs into `main`, never commits to `main`. Write clear commit messages.
- Before each feature is handed over, it must pass `/code-review` and be verified (see the per-change gate below).
- Ask for credentials (AWS, OCR provider, Expo/EAS) only at the step that needs them.
- Flag up front anything that could degrade experience, performance, cost or delivery. `UPDATE_PLAN.md` asks for this explicitly.
- Model plan: a strong model (Opus) leads architecture, shared code, review and sign-off. Cheaper agents (Sonnet) take self-contained ports or features against a written contract (see `tools/verify/PORTING.md` for the pattern). Keep fan-out under about 10 agents per chunk.

## Session 2 plan (agreed order)

### Gate A — setup
1. Run a skill audit (`/skill-doctor`). Remove or disable unused skills and plugins, and record the result in `docs/SKILLS_AUDIT.md`. Confirm `/loop` is available.
2. Write personas into `docs/PERSONAS.md`. `/deep-research` isn't installed, so use cited web research. Write 3–5 Ghanaian SME personas, for example:
   - a market trader on MoMo
   - a pharmacy owner with stock
   - a services firm with an accountant
   - a growing retailer on Excel

   For each, cover devices, connectivity, literacy, tools, pain points and success criteria.
3. Restructure `docs/UPDATE_PLAN.md` into `docs/PRD.md`: goals, per-feature requirements, non-goals, risks and acceptance criteria. Adopt SemVer (v1.0.0 = the React migration), add `CHANGELOG.md` in Keep a Changelog format, and tag releases.

### Gate B — features
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
- The workspace shell is about 100 KB gzip on first load, up from 29 KB. That matters on mobile data, so consider a lighter router or other ways to shrink it.
- After switching file with a preset range, the old date window renders for a moment. The cause is in `useScopedQuery`, `frontend/src/app/hooks.ts`.
- The Product name column never sorts Z→A (`frontend/src/app/views/products.logic.ts`, `nextSort`). This was kept for parity.
- Open PRs #10 and #11 change the deleted legacy frontend and need rebasing onto the React views.
- A real AI provider and a real Brave research run were never exercised. Only a mock LLM was used.

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

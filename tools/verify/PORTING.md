# Ferlance view porting contract (React + Vite + TS)

Repo: /home/primeyloa/Code/databloom/ferlance. Branch `feat/react-migration` (already checked out; do NOT commit, push, or switch branches — the lead commits).
Goal: **exact visual and behavioural parity** with the legacy vanilla-JS view. No redesign, no new features, no copy changes.

## Read first
- Legacy view logic: `frontend/legacy/assets/js/app/views/<name>.js` (+ `shared.js`, `dom.js`, `state.js`, `reports.js`)
- Legacy static markup for the view: `frontend/legacy/index.html` — the `<section class="view" data-view="<name>">` block
  (overview :93, products :139, insights :156, lance :178, inventory :205, position :261, data :298, settings :349).
- Foundation you build on (read, don't edit):
  - `src/app/workspace.tsx` — `useWorkspace()` → `{ user, business, businessPath, datasets, refreshDatasets, inventory, refreshInventory, setup, markSetup, updateIdentity }`; `useScope()` → `{ scope, setScope, bounds, setBounds, range, params, label, hasData }`; `keys` (query keys).
  - `src/app/hooks.ts` — `useScopedQuery<T>('/analytics', { updatesBounds: true })` for scoped reads; `useBusinessQuery<T>('/inventory/movements?limit=100')` for unscoped reads.
  - `src/app/components/ui.tsx` — `Pill, Delta, Kpi, EmptyState, SkeletonRows, Notice, StatusText, Segmented, DataTable` (+ `Column`, `SortState`).
  - `src/app/views/shared.tsx` — `InsightCard, RankItems, StatusPill, AttentionItem`.
  - `src/app/page.tsx` — `<PageActions>` portals the view's top-bar buttons (legacy `view.actions()`).
  - `src/app/routes.tsx` — `pagePath('inventory')` → `/app/inventory`.
  - `src/lib/` — `api.ts` (`request<T>(path, { method, json, body, signal })`, `ApiError`), `format.ts` (money, number, percent, plainPercent, formatDate, formatDateTime, isoDate, plural, `safeHref`), `icons.tsx` (`<Icon name>`, `<IconSlot name>`), `toast.tsx` (`toast(msg, { error })`), `markdown.tsx` (`<Markdown source>`), `chart/BarChart.tsx`, `reports.tsx` (print functions take `{ business, user }` as last arg), `types.ts`.

## Rules
1. File: `src/app/views/<Name>.tsx`, `export default function <Name>()`. The Shell already renders the `<section class="view" data-view=...>` wrapper and the page title/description — render only the section's *inner* content.
2. **Markup parity**: same elements, class names, ids, `aria-*`, `role`, `data-*` attributes and text as the legacy static HTML **plus** what the legacy JS generated. CSS (`src/styles/*.css`, unchanged) targets these. Where legacy HTML had `<span data-icon="x"></span>` use `<IconSlot name="x" />`; where an element itself carried `data-icon` (icon buttons) keep `data-icon` on it and put `<Icon>` inside.
3. **Data**:
   - Scoped endpoints (`/analytics`, `/insights`, `/questions/{id}`, `/performance-research`, `/ask-lance`) use the current scope. For GETs use `useScopedQuery`. Pass `updatesBounds: true` wherever the legacy code assigned `state.bounds = ...available_period`.
   - Unscoped reads: `useBusinessQuery`. Datasets and inventory already live in `useWorkspace()` — don't refetch them separately.
   - Writes: `request()` (or TanStack `useMutation`), then refresh caches: `refreshDatasets()`, `refreshInventory()`, or `queryClient.invalidateQueries({ queryKey: keys.business(business.id) })` (prefix match) as appropriate.
   - Load errors are already toasted globally by the query client (except 401). Action errors: `toast(error.message, { error: true })` or the view's `StatusText`, matching legacy.
   - `legacy state.setup.x = true` → `markSetup({ x: true })`. `state.user/business` updates → `updateIdentity()`.
   - Use `AbortSignal` from the query fn (handled by hooks) — never `setState` after unmount.
4. **Links**: legacy `href="#page"` → `<Link to={pagePath('page')}>` from `react-router`. External URLs from API data → `href={safeHref(url)}` with `target="_blank" rel="noopener noreferrer"`.
5. **Security**: never `dangerouslySetInnerHTML`/`innerHTML` (lint enforces). Render user/upload data as text.
6. **Types**: declare view-specific response types at the top of your view file. Use `src/lib/types.ts` types where they fit. Strict TS — no `any`; `unknown` + narrowing if needed.
7. **Do not edit shared files** (`src/lib/**`, `src/app/*.tsx|ts`, `src/app/components/**`, `src/app/views/shared.tsx`, styles, configs). Other agents are working in parallel. If you need a missing shared helper, write a local one in your view file and **list it in your final report** so the lead can promote it.
8. Put non-trivial pure logic (sorting, filtering, derived rows, CSV building) in exported functions in `src/app/views/<name>.logic.ts` and cover them with `src/app/views/<name>.logic.test.ts` (vitest, globals enabled).
9. Hooks rules / exhaustive deps must pass lint. Prefer derived values over effects; no effect-driven state syncing where a computed value works.

## Verify before reporting (all must pass for YOUR files)
```bash
cd /home/primeyloa/Code/databloom/ferlance/frontend
npx tsc --noEmit -p tsconfig.json 2>&1 | grep -E "views/(<Name>|<name>)" || echo "types ok"
npx eslint src/app/views/<Name>.tsx src/app/views/<name>.logic*.ts
npx vitest run src/app/views/<name>
```
Visual parity — use YOUR OWN backend (a private copy of the seeded demo data, so your test writes don't disturb other agents):
```bash
/tmp/ferl-tools/serve.sh <BACKEND_PORT> /tmp/ferl-<batch> &      # FastAPI on your port, data dir already seeded
cd /home/primeyloa/Code/databloom/ferlance/frontend
FERLANCE_API=http://127.0.0.1:<BACKEND_PORT> npx vite --port <YOUR_PORT> --strictPort &   # kill both when done
node /tmp/ferl-tools/viewshot.mjs http://127.0.0.1:<YOUR_PORT> <name> /tmp/ferl-shots/after
```
Then **Read** your screenshots and the matching `/tmp/ferl-shots/before/<name>-{light,dark}-{desktop,phone}.png` and fix any difference (layout, spacing, missing elements, text). Console errors must be none (except a 403 from `/api/admin/capabilities` on Settings, which is expected for non-admins).
Also exercise the view's interactions in a quick Playwright script if it has forms/actions (submit with the seeded demo user; it's a throwaway data dir).

## Final report (keep it short)
- Files created.
- Behaviours ported (checklist against legacy) and anything you could NOT reproduce exactly, with reason.
- Local helpers that should be promoted to shared files.
- Verification results (tsc/eslint/vitest output summary; screenshot comparison verdict per theme/size).

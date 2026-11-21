# Ferlance product requirements: update phase (v1.x)

| | |
| --- | --- |
| Status | Draft for owner review |
| Baseline | v1.0.0, the React + TypeScript migration (PR #12, merged 2026-11-21) |
| Supersedes | `docs/UPDATE_PLAN.md`. The owner's original brief is kept verbatim in the appendix. |
| Related | `docs/PERSONAS.md`, `docs/ARCHITECTURE.md`, `docs/DATA_CONTRACT.md`, `docs/HANDOFF.md`, `CHANGELOG.md` |

## 1. Goals

1. **Less typing and more trust in stock and sales data.** Capture inventory from photos and documents (OCR), and keep the inventory and product catalogues in sync.
2. **Owners can bring their team in.** A guided onboarding flow, and an admin console for platform operators.
3. **A more mature, intentional interface.** One documented design system, with analytics visuals that are animated, responsive and accessible.
4. **Better answers from Ask Lance.** Improve retrieval only where it measurably helps, without slowing the app or adding running cost.
5. **Data out, for growth.** A durable, low-cost export path to AWS for analysis outside the app.
6. **Mobile.** An Expo app for iOS and Android, used for internal testing in this phase.

Every goal is judged against the four personas in `docs/PERSONAS.md`: a market trader on MoMo, a pharmacy owner, a services firm with an accountant, and a growing retailer on Excel.

## 2. Principles (unchanged from ARCHITECTURE.md)

- Deterministic numbers are the source of truth. The LLM explains numbers and never produces them.
- Missing is not zero. Nothing is dropped silently. One scope everywhere.
- No placeholder features. Each feature ships end to end or not at all.
- **New in this phase:** the low-end Android phone on mobile data is the reference device. A feature that regresses first-load weight or interaction latency there has to justify it in its PR.

## 3. Release plan and versioning

Ferlance follows [Semantic Versioning 2.0.0](https://semver.org/). The version lives in `frontend/package.json` and in `FastAPI(version=…)` in `backend/main.py`, and the two must match. Each release is tagged `vX.Y.Z` on its `main` merge commit and has an entry in `CHANGELOG.md` ([Keep a Changelog](https://keepachangelog.com/en/1.1.0/)).

- **MAJOR:** an incompatible API or data change, such as a breaking change to an endpoint shape or a migration that cannot be rolled back.
- **MINOR:** each feature below.
- **PATCH:** fixes and follow-ups.
- Docs-only and tooling-only changes stay under *Unreleased* and ship with the next release.

| Version | Content | Features |
| --- | --- | --- |
| 1.0.0 | React migration (parity) | done |
| 1.0.x | Migration follow-ups (§5.0) | F0 |
| 1.1.0 | Design system and interface refinement | #7 |
| 1.2.0 | Analytics visuals | #6 |
| 1.3.0 | Onboarding and team access, admin console | #4, #5 |
| 1.4.0 | OCR inventory capture | #1 |
| 1.5.0 | Inventory↔product sync | #2 |
| 1.6.0 | Retrieval improvements for Ask Lance | #8 |
| 1.7.0 | Data export to AWS | #3 |
| 1.8.0 | Expo mobile app (internal testing) and shared API types | #9 |

The order follows the agreed handoff plan. #6 builds on the #7 tokens. #2 reuses the #1 review flow. #3 and #9 carry the most external cost and credentials, so they come last.

## 4. Process (per-change gate)

Each feature has its own `feat/*` branch off `main` and its own PR. A PR is ready for the owner only when all of these are true:

1. **Persona check.** The PR description holds the persona table from `docs/PERSONAS.md`. It answers "Does the app provide ease, comfort and value to the Ghanaian SME?" for each persona the change targets. `/loop` runs a prompt on an interval, so it suits iterating on a change until the check passes, not a one-shot review. A one-shot check in the PR is the default.
2. **Verification.** The following must all pass:
   - `npm --prefix frontend run check`
   - `npm --prefix frontend run build`
   - `.venv/bin/pytest -q`
   - a browser check of the changed screens in light and dark at phone width (360–390 px) and on desktop, using `tools/verify`
   - for UI changes, the gzip size of the entry bundles, before and after
3. **`/code-review`.** Run it on the diff and apply the fixes. Add `/security-review` for anything touching auth, uploads, roles, secrets or external services.
4. **Release bookkeeping.** Add a CHANGELOG entry, bump the version in both places, and tag after merge.

Credentials (AWS, OCR provider, Expo/EAS) are requested only at the step that needs them. Secrets go in environment variables or the encrypted `business_integrations` store, and never in git.

## 5. Feature requirements

### 5.0 F0: Migration follow-ups (v1.0.x)

| ID | Requirement | Acceptance |
| --- | --- | --- |
| F0.1 | Shrink the workspace first load, about 100 KB gzip today against 29 KB before the migration | Done in v1.0.1. The measured breakdown of the shell's minified JS was react-dom 65%, react-router 12%, TanStack Query 10% and app code 9%. React alone is about 60 KB gzip, so the original 60 KB target cannot be met on React. The budget is now **first-visit JS+CSS for `/app/overview` at 110 KB gzip or less on the wire**: v1.0.1 measures 108 KB, against about 383 KB before, because the server sent everything uncompressed. App-only releases should re-download 15 KB gzip or less (the vendor chunk is cached separately). Going further needs Preact (an owner decision, §8). |
| F0.2 | Stop the old date window flashing after a file switch with a preset range (`useScopedQuery`) | Done in v1.0.1. Each dataset stores its record date span, so presets resolve before the first request. |
| F0.3 | Product name sort can go Z→A (`nextSort`) | Done in v1.0.1 |
| F0.4 | Exercise a real AI provider and a real Brave research run once | A recorded run with the owner's keys. Credentials are requested at this step. |

### 5.1 #7: Design system and interface refinement (v1.1.0)

**Why:** The interface should feel mature and intentional. The owner's reference is a multi-brand, platform-agnostic design system (EarnIn, on Dribbble). We take its *principles*: tokens organised by tier, a component inventory, density and consistent rhythm. We do not copy its visuals or brand.

| ID | Requirement | Acceptance |
| --- | --- | --- |
| 7.1 | A three-tier token system: primitive → semantic → component. It extends `src/styles/base.css` and keeps the current Lev-derived identity. | The tokens are documented in `docs/DESIGN_SYSTEM.md`. Light and dark both come from the semantic tier. No hard-coded colours outside the token files (checked with grep or lint). |
| 7.2 | A component inventory of the primitives in use: buttons, inputs, pills, cards, tables, dialogs, empty, loading and error states | Each primitive has documented variants and states, and is used consistently on every page |
| 7.3 | Responsive pass | No horizontal scroll at 360 px. Tap targets are at least 44 px. Tables have a phone layout. |
| 7.4 | Accessibility | WCAG 2.2 AA contrast in both themes, visible focus and keyboard reachability. An axe pass shows no serious violations. |
| 7.5 | The token set is shareable with design tools | Optional: export to Figma through the Figma connector for owner review |

**Non-goals:** a brand-new identity, a component library package, or theming per business.

### 5.2 #6: Analytics visuals (v1.2.0)

| ID | Requirement | Acceptance |
| --- | --- | --- |
| 6.1 | Circular visuals where they fit the data: a donut or ring for composition (revenue share by product or channel) and radial progress for goals or completeness, such as data completeness and the setup guide | Each chart has a text or table equivalent. Values are always labelled, never colour-only. |
| 6.2 | Animated and responsive charts | Transitions are 300 ms or less, run on the GPU (transform and opacity), and are disabled under `prefers-reduced-motion`. Charts resize with their container, with no layout shift. |
| 6.3 | Keep charts dependency-light | Extend the in-house SVG chart (`src/lib/chart`) first. A library is added only if it costs no more than 15 KB gzip on the routes that use it, and it is lazy-loaded. |
| 6.4 | Charts read the same scope as everything else | They use the existing scoped queries, with no new data paths |
| 6.5 | Honest visuals | A donut is never used for more than about 6 categories (the rest go into "Other"). Missing costs show as "missing", not as zero. |

**Risk:** Animation on low-end Android. Mitigation: profile on a throttled CPU in the browser check.

### 5.3 #4/#5: Onboarding, team access and admin console (v1.3.0)

**Current state:** `backend/routers/admin.py` already provides `GET /api/admin/capabilities`, `GET /api/admin/users` and `PATCH /api/admin/users/{id}/role`, gated by `FERLANCE_ADMIN_EMAILS`. Settings already has an admin card. This feature *extends* what exists. It does not build a second console.

| ID | Requirement | Acceptance |
| --- | --- | --- |
| 4.1 | First-run onboarding driven by real state. The existing setup guide becomes a short guided flow: business profile, first import (file or MoMo SMS), optional stock, then a first question. | It can be skipped and resumed. Every step writes real data. No questionnaire whose answers go unused (ARCHITECTURE "What was removed"). |
| 4.2 | Team access: the owner invites a member (manager, accountant) to a business with a role | Invite by link or code, with expiry and single use. Roles are enforced server-side on every business-scoped route. There are tests for cross-tenant and cross-role denial. |
| 4.3 | Admin console for platform operators | Users and businesses list with search, role management, account disable and enable, and an audit log of admin actions. Admin routes go through `/security-review`. |
| 4.4 | Onboarding status is visible to admins | Admins can see who stalled at which step (aggregate counts, no business data) |

**Non-goals:** billing, impersonation, or SSO.

**Risk:** The role model touches every router. Mitigation: one dependency in `deps.py`, plus a test matrix.

### 5.4 #1: OCR inventory capture (v1.4.0)

| ID | Requirement | Acceptance |
| --- | --- | --- |
| 1.1 | Capture a photo or PDF of an invoice, delivery note or stock list. On phone this uses the camera. | Upload works on a flaky connection (retry, size cap, client-side image downscale) |
| 1.2 | Extract line items: name, quantity, unit cost, SKU and expiry where present | Field-level confidence is shown. The fixture set records the extraction accuracy. |
| 1.3 | **Review before write.** Extracted lines are a draft. The owner confirms, edits or rejects each line before any stock movement is written. | Nothing reaches the inventory ledger without confirmation. Rejected lines are kept with their reason. |
| 1.4 | Matching to existing products (exact SKU, then fuzzy name) with a suggested match | The owner can accept, change or create a product |
| 1.5 | The provider is pluggable behind one interface, chosen on cost and privacy, with a local fallback | Provider choice and cost per page are in the PR. The provider key is stored like other integration keys. |

**Risks:** Per-page provider cost. Supplier documents go to a third party (privacy), so this must be disclosed in the UI. Accuracy on low-quality photos.

**Decision needed at build time:** the provider. Candidates: a hosted OCR or document-AI API, a vision-capable LLM through the existing router, or local Tesseract as the fallback.

### 5.5 #2: Inventory↔product sync (v1.5.0)

Today, sales files never change stock (by design), and inventory products and sales products are separate name spaces.

| ID | Requirement | Acceptance |
| --- | --- | --- |
| 2.1 | Product mapping: link sales product names (including per-shop variants) to inventory products | A mapping UI with suggestions. Unmapped names are listed, never dropped. |
| 2.2 | Optional sales→stock posting: the owner opts in per business and per import, and mapped sales post `sale` movements | It is idempotent per dataset. Excluding a file reverses its movements. The ledger still cannot go negative: conflicts are surfaced, not clamped. |
| 2.3 | Reconciliation view: expected stock vs counted stock | Variance by product after a stocktake |
| 2.4 | Shared review components with OCR (#1) | Same draft→confirm pattern |

**Risk:** Double-counting when a file is re-imported. Mitigation: the existing checksum and duplicate detection, plus idempotency keyed on the dataset.

### 5.6 #8: Retrieval improvements for Ask Lance (v1.6.0)

| ID | Requirement | Acceptance |
| --- | --- | --- |
| 8.1 | Measure first: a small eval set of real-shaped questions over the seeded demo data, scored for retrieval hit rate and answer grounding | A baseline score for the current FTS5 pipeline |
| 8.2 | Try hybrid retrieval: `sqlite-vec` embeddings next to FTS5 (reciprocal-rank fusion), in the same SQLite file | Adopt it only if it improves the eval, adds no more than 100 ms p95 to Ask Lance retrieval at demo scale and adds no hosted service. Embedding cost per import must be stated. |
| 8.3 | Keep deterministic answers deterministic | Instant questions and metrics never go through retrieval |

**Non-goal:** a hosted vector database. Reconsider it only if the per-business data outgrows SQLite.

### 5.7 #3: Data export to AWS (v1.7.0)

**Recommendation:** At SME scale a full data lake (Glue catalogue, Lake Formation, Athena over many sources) is overkill. It adds standing cost and operational load without improving the app. Start with a **scheduled, per-business Parquet export to S3**, partitioned by business and date. Athena can query it on demand, so it costs nothing while idle. It can grow into a lake later without rework.

| ID | Requirement | Acceptance |
| --- | --- | --- |
| 3.1 | Scheduled export of normalised records, inventory movements and balances to S3 as Parquet | Runs off the request path. Failures are visible in admin. Monthly cost estimate in the PR. |
| 3.2 | Least-privilege IAM: a write-only role for the exporter. Encryption is on (SSE-S3 or KMS). | The IAM policy is reviewed in the PR. No AWS keys in git. |
| 3.3 | Tenant isolation is kept in the lake layout | One prefix per business. Deleting a business deletes its prefix. |
| 3.4 | Opt-in per deployment (environment config). The app runs unchanged without AWS. | Tests pass with AWS unset |

**Risks:** cost if exports are too frequent or unpartitioned, and data-residency questions for business records. **Credentials needed at this step:** an AWS account, region, bucket and IAM role.

### 5.8 #9: Expo mobile app (v1.8.0, internal testing)

| ID | Requirement | Acceptance |
| --- | --- | --- |
| 9.1 | An Expo (React Native) app for iOS and Android covering sign-in, Overview, MoMo SMS paste, Ask Lance and OCR capture | Runs in Expo Go and as an EAS internal build |
| 9.2 | Shared API types: move `frontend/src/lib/types.ts` (and the API client contract) into a shared package used by web and mobile | One source of types. The web build is unchanged. |
| 9.3 | Auth suited to mobile: refresh tokens in the secure store. The backend must accept non-cookie refresh for mobile clients without weakening the web flow. | A security review of the auth change |
| 9.4 | Works on a budget Android phone on 3G | Cold start and screen timings recorded in the PR |

**Non-goals:** a store release or push notifications (later). **Credentials needed at this step:** an Expo/EAS account. Apple and Google developer accounts are needed only for later store builds.

## 6. Cross-cutting non-goals for v1.x

- Rewriting the backend, or replacing SQLite as the primary store.
- Multi-currency conversion. Mixed currencies are still reported, never summed.
- Payments, billing or subscriptions.
- External database connectors (removed for security reasons, see ARCHITECTURE).

## 7. Risks register

| Risk | Affects | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- | --- |
| First-load weight on mobile data | All | High | High | F0.1 bundle budget, lazy routes, and size checked in every UI PR |
| Animation jank on low-end Android | #6 | Medium | Medium | Transform and opacity only, reduced-motion, throttled-CPU check |
| OCR running cost and privacy | #1 | Medium | High | Pluggable provider, cost per page in the PR, disclosure, review before write |
| Role model regressions (tenant leaks) | #4 | Medium | Critical | One dependency, a denial test matrix, `/security-review` |
| Stock double-counting from sync | #2 | Medium | High | Opt-in posting, idempotency per dataset, reversal on exclude |
| Embeddings slow imports or add cost | #8 | Medium | Medium | Eval-gated adoption, latency budget, no hosted service |
| AWS standing cost and misconfiguration | #3 | Medium | High | Export-first design, least-privilege IAM, cost estimate, opt-in |
| Mobile auth weakens web security | #9 | Low | High | Separate mobile refresh path, security review |
| Copying the reference design too closely | #7 | Low | Medium | Principles only, keep the Ferlance identity |
| Only a mock LLM has been used, never a real provider | #8, Ask Lance | High | Medium | F0.4 real-provider run |

## 8. Open decisions (asked at the step that needs them)

1. The OCR provider (#1): cost against accuracy against privacy.
2. Whether sales→stock posting (#2) is off by default (recommended) or on.
3. AWS account, region and the residency stance (#3).
4. Expo/EAS account (#9).
5. Disabling the unused account-level skills and connectors (`docs/SKILLS_AUDIT.md`).
6. Whether to swap React for Preact (`preact/compat`) to cut about 55 KB gzip from the first visit. The cost: it reverses the React 19 choice, and React 19 APIs, Testing Library and TanStack Query would need re-verifying.

## Appendix: the owner's original brief (verbatim, from `docs/UPDATE_PLAN.md`)

> This is a skirmish for the update to be done after the migration of the interface for Ferlance
>
> This update features addition of new features, changing or updating old ones, moving on from old practices and testing existing ones to see where they break and where or how to fix them (you do them)
> The use of skills are not limited to what were indicated in the prompt, but they are a personal preference or a starter.
>
> The proposed updates:
> 1. OCR for updating and adding products to inventory
> 2. Syncing inventory and products (The motivation and idea are in similar vein).
> 3. Setting up and connecting to a data lake with AWS (thinking of doing this for the application) - prompt me where this or any other change or current inclusion, or possible direction may degrade the experience, performance or delivery of the proposed idea. Setup this up; prompt me for any credentials or details needed.
> 4. Onboarding steps/flow for users connected to an admin management console such that admins (admin users)
> 5. Develop (or prompt me if there already exists an admi nmanagement app or endpoint/suite within the app)
> 6. Better analytics design (use circular charts, animated and responsive visuals - use a design system or skill from the internet that would support this)
> 7. App-wide interface update/tweak (more responsive, clear interface giving off a more mature, intentional vibe; https://dribbble.com/shots/23850607-EarnIn-s-platform-and-device-agnostic-multi-brand-design-system . You can observe the video from this link to design a design system or update fetched, already existing or created one.
> 8. Suggesting update and improvement of RAG to a proper RAG with a vector database (if necessary - avoid if slows down app considerably or costs too much)
> 9. Implement mobile app version that works across IOS and android via expo for testing. Mobile app release would come later.
>
> You can break this down or update this document itself to give a more comprehensive and well structured or plan for the update (restructure and update this document first before starting updates)
> You can also break down these updates to planned chunks since they are huge updates (so as to avoid burning up too many tokens at once). But if you can, do it all in one session, fanning out subagents for each subtask or feature or skill - ensure a master agent to sign off, sync and avoid clashes over the devlopment process.
> Form or update a PRD stating and giving all information about requirements, changes, updates and keep track of app versions using a robust or standard versioning approach

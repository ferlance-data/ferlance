# Changelog

All notable changes to Ferlance are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html). The version is kept in `frontend/package.json` and `backend/main.py`, which must match. Each release is tagged `vX.Y.Z` on its merge commit to `main`. The release plan is in `docs/PRD.md`.

## [Unreleased]

## [1.4.0] - 2026-11-22

Team access (PRD §5.3, 4.2): owners give managers and accountants their own sign-in.

### Added
- Business roles: **owner**, **manager** and **accountant**. The server enforces them on every business route through declared permissions.
  - Accountants can see everything, record balances and use AI, but can't change sales or stock.
  - Managers can do everything except manage the team or rename the business.
- Invite links from Settings → Team. They are single-use, expire after 7 days and can be cancelled, and are shared by copy and paste (for example on WhatsApp).
  - New people sign up through the link without creating a business. Existing users sign in through it.
  - The token is removed from the address bar once it has been read.
- The owner can change a member's role or remove them, and it takes effect on their next request.
- A business switcher in the sidebar for people who belong to more than one business.
- A daily cap on uncached AI calls per business (`FERLANCE_AI_DAILY_LIMIT`, default 100), shared by Ask Lance and the explanations.
- The Data and Inventory pages show a clear read-only notice instead of forms the user's role can't use.

### Changed
- Renaming the business moved to `PATCH /api/businesses/{id}` (owner only). `PATCH /api/auth/profile` now updates only your own name.
- `/api/auth/me` also returns `businesses`, with your role in each.
- Refresh tokens: a token rotated in the last 60 seconds can be used once more, if its replacement was never used. This stops users on flaky connections being signed out when a refresh response is lost. Signed-out tokens never get this grace.

### Fixed
- The landing page's privacy copy still described the removed Brave web research.

## [1.3.0] - 2026-11-22

Analytics visuals (PRD §5.2, #6): circular, animated and responsive, accessible, and with no chart library.

### Added
- Donut charts:
  - "Where your revenue comes from", on Overview and Products
  - "Where your profit comes from", on Products, when costs are complete
  - Each shows the top five products plus Other. Tap or hover a slice to see its share.
- "How complete your records are" on Overview: progress rings for product, cost, quantity and customer coverage, each saying what it unlocks. `/analytics` now returns `coverage`.
- A validated categorical chart palette (`--chart-cat-1`…`5`, `--chart-other`) for both themes.
- Bar chart: tooltips work on touch, and a "Show as table" view is added.

### Changed
- The setup guide's progress bar is now a progress ring.
- Bars, slices and rings animate in once (0.3 s or less, transform and opacity only). Nothing animates under reduced motion.

## [1.2.0] - 2026-11-22

Insights that say what to do. Free outside context replaces paid search.

### Added
- **What to do now:** ranked, plain-language suggestions on Insights (all of them) and Overview (top 3), calculated from the business's own records without AI:
  - which product to sell more of
  - products selling less, or no longer selling
  - products losing money, with the price that would break even
  - margins being squeezed, with the price that restores the old margin
  - stock about to run out, with how much to order (matched to inventory by exact name)
  - money tied up in slow stock
  - dependence on one product or one customer
  - the busiest day of the week
- Each suggestion explains **why it may be happening**, labelled *likely* or *possible*: price vs volume, fewer vs smaller sales, regular buyers who stopped (named for the owner only), out of stock, the same pattern last year, or Ghanaian holidays and seasons. It also lists **what to do**.
- **Tap for details:** a sheet shows the numbers, reasons and actions. When an AI key is configured, it also shows Lance's short explanation, cached so repeat taps are free.
- A Ghana calendar (`ghana_calendar.py`) of statutory holidays, Easter, Eid and Ramadan (approximate), the festive season, back-to-school periods and weather seasons.
- Free, keyless news context from the GDELT index (`news_context.py`). It is used for explanations and by Ask Lance, rate-limited and best effort.
- "Get sharper suggestions" lists the missing columns (cost, quantity, customer, history) that would unlock more advice.

### Changed
- Ask Lance's search tool is now `news_search` (free GDELT headlines). It replaces the paid SerpAPI web search.

### Removed
- Brave Search web research: the Settings card, `/integrations/brave-search`, `/performance-research`, and stored Brave keys, which are deleted on upgrade.
- The `SERPAPI_KEY` setting.

## [1.1.0] - 2026-11-22

The design system and interface refinement (PRD §5.1, #7). It keeps the existing identity and makes it accessible, touch-friendly and lighter. See `docs/DESIGN_SYSTEM.md`.

### Added
- A component token tier for button, input, pill, card, table, dialog, toast and nav item, plus spacing, motion and z-index scales.
- A colour lint in `npm run check`. Colour literals are allowed only in token declarations.
- `docs/DESIGN_SYSTEM.md`: tiers, rules, the measured contrast table, the component inventory and fonts.
- A phone layout for data tables: each row becomes a labelled card, so no column is hidden off-screen.
- 44 px touch targets on touch screens. Compact controls get an invisible hit area, so desktop density is unchanged.

### Changed
- Fonts are self-hosted and preloaded, subset to Latin-1, the cedi sign and Ghanaian letters (ɛ ɔ ŋ ɖ ƒ ɣ ʋ). That is 92.6 KB from our own origin, against about 152 KB from two Google origins.
- Contrast was measured in both themes and fixed:
  - muted text is 4.5:1 on muted surfaces
  - AI-labelled text is 4.5:1
  - input borders and the focus ring are 3:1
  - landing grey text is 5.3:1
- Chart revenue and cost colours were re-picked per theme with a palette validator (colour-blind separation, and 3:1 against the surface).
- The smallest text is now 12 px. The 10, 10.5 and 11 px sizes are gone.

### Fixed
- On phones, the icon-only Print and New chat buttons had no accessible name.
- The setup progress bar had no accessible name.
- The Ask Lance conversation could be scrolled but not reached by keyboard.


## [1.0.1] - 2026-11-22

Migration follow-ups (PRD F0.1–F0.3). A first visit to the workspace now downloads about 108 KB instead of about 383 KB.

### Added
- Responses are gzip-compressed: bundles, HTML and API JSON. Auth responses are left uncompressed, so token sizes cannot leak (BREACH).
- The sign-in dialog prefetches the workspace bundle, so the app opens from cache after sign-in. This is skipped when the browser asks to save data.
- Each dataset reports its record date span (`period`). Existing files are backfilled once at startup.
- `docs/PRD.md`: product requirements for the v1.x update phase. It replaces `docs/UPDATE_PLAN.md` and keeps the original brief as an appendix.
- `docs/PERSONAS.md`: four cited Ghanaian SME personas and the per-change persona check.
- `docs/SKILLS_AUDIT.md`: an audit of the Claude Code skills and connectors used for development.
- `docs/HANDOFF.md` and `tools/verify/`: the session handoff, and the parity and e2e verification scripts used for the migration.
- This changelog.

### Changed
- Third-party code ships in its own `vendor` chunk. It keeps its cache across app-only releases, so returning users re-download about 11 KB instead of the whole bundle.
- `react-router` is replaced by a small in-house router (`src/lib/router.tsx`). It saves about 11 KB gzip and keeps the same behaviour: modified clicks open new tabs, `aria-current` on active links, back/forward, legacy `#page` redirects, and transition-based page loads.
- The Product name column now toggles between A→Z and Z→A, like the other columns.

### Fixed
- After switching file with a preset range such as "Last 30 days", the previous file's date window no longer shows briefly. Presets now resolve from the file's stored date span before the first request, and the extra request is gone.
- Opening a scoped page other than Overview, Products or Insights first (for example Ask Lance) no longer anchors presets to today instead of the latest record.

## [1.0.0] - 2026-11-21

The first versioned release. The frontend was migrated to React 19, TypeScript (strict) and Vite with feature parity (PR #12).

### Added
- React single-page workspace at `/app/*` with React Router pages. Old `#page` links redirect.
- TanStack Query caching. Scoped reads put the resolved file and date scope in the cache key.
- A typed API client. The access token is held in memory only, and concurrent 401s share one refresh.
- Error boundaries contain page crashes. Ask Lance threads persist across navigation.
- Hashed assets are served with immutable caching. Entry HTML is served `no-cache`.

### Changed
- The landing page keeps static markup, with a small TypeScript module for its interactions.

### Removed
- The pre-React frontend (`frontend/legacy/`).

### Known issues
- The workspace shell is about 100 KB gzip on first load, up from 29 KB.
- The old date window briefly renders after a file switch with a preset range.
- The Product name column never sorts Z→A. This was kept for parity.

[Unreleased]: https://github.com/ferlance-data/ferlance/compare/v1.4.0...HEAD
[1.4.0]: https://github.com/ferlance-data/ferlance/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/ferlance-data/ferlance/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/ferlance-data/ferlance/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/ferlance-data/ferlance/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/ferlance-data/ferlance/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/ferlance-data/ferlance/releases/tag/v1.0.0

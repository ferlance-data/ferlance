# Changelog

All notable changes to Ferlance are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html). The version is kept in `frontend/package.json` and `backend/main.py`, which must match. Each release is tagged `vX.Y.Z` on its merge commit to `main`. The release plan is in `docs/PRD.md`.

## [Unreleased]

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

[Unreleased]: https://github.com/ferlance-data/ferlance/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/ferlance-data/ferlance/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/ferlance-data/ferlance/releases/tag/v1.0.0

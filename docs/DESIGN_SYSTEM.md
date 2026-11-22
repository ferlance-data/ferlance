# Ferlance design system

This document describes how Ferlance looks and why: the tokens, the components, and the rules that keep both themes accessible on a budget Android phone. It covers v1.1.0 (PRD §5.1, #7).

## Identity (unchanged)

The visual language comes from the October 2026 redesign (see `ARCHITECTURE.md`, "Product benchmarks"):

- IBM Plex Sans for text and IBM Plex Mono for numbers and eyebrows
- deep ink-green surfaces with a mint accent
- hairline rules and pill-shaped controls
- tight, medium-weight headlines

The marketing page is always dark. The workspace is light, with a dark theme.

The owner pointed to a multi-brand, platform-agnostic design system on Dribbble as a reference. Only its general principles were taken: tiered tokens, a component inventory with documented states, one rhythm across platforms, and the same tokens reused by the coming mobile app (#9). Ferlance's own visuals were kept. The Dribbble page could not be read (it returned no content), so nothing specific was copied from it.

## Token tiers

All tokens live in `frontend/src/styles/base.css`.

| Tier | Purpose | Examples | Who may use it |
| --- | --- | --- | --- |
| **Primitive** | Raw values: palette steps, alpha steps, print greys, chart colours | `--ink-950`, `--mint-500`, `--fog-600`, `--white-a08`, `--viz-mint-600` | Semantic and component tokens. Rules only for brand-fixed artwork, such as the landing page and the brand mark. |
| **Semantic** | Meaning, redefined per theme under `:root[data-theme="dark"]` | `--background`, `--surface`, `--foreground`, `--muted-foreground`, `--border`, `--cta`, `--ring`, `--success-*`, `--warning-*`, `--error-*`, `--info-*`, `--ai-*`, `--chart-*` | Every workspace rule |
| **Component** | Dimensions and states of shared primitives | `--button-height`, `--input-radius`, `--pill-height`, `--card-padding-x`, `--table-cell-padding`, `--dialog-backdrop`, `--toast-padding`, `--nav-item-height` | The component's own rules. Retune a component here, not at its call sites. |

Scales sit alongside the tiers:

- **Spacing:** `--space-*`, a 4 px base with the half steps the layout already uses.
- **Type:** `--text-2xs` to `--text-2xl`. **The floor is 12 px**: nothing on screen is smaller. Print styles are exempt.
- **Radius:** `--radius-*`.
- **Motion:** `--duration-fast`, `--duration-base`, `--duration-slow` and `--ease-out`. Everything collapses to near zero under `prefers-reduced-motion`.
- **Elevation:** `--shadow-*` and `--z-nav`, `--z-toast`.

Rules:

1. **No colour literals outside token declarations.** `npm run check` enforces this (`frontend/scripts/lint-colors.mjs`):
   - In CSS, a `#hex`, `rgb()` or `hsl()` value may appear only in a `--token: …` declaration.
   - In TS/TSX, a string that is just a colour is an error unless the line says `color-lint: allow`. Today the only such line is the browser `theme-color` meta, which must be a literal.
2. **Don't rename semantic tokens.** Features #6 onward, and the mobile app, build on them. Add a new token instead.
3. **SVG drawn from TypeScript takes colours as `style.fill = 'var(--token)'`**, because presentation attributes don't resolve `var()`. The landing skyline is an example.

## Accessibility contract

Contrast was measured from the built CSS in both themes, not estimated:

| Pair | Minimum | Light | Dark |
| --- | --- | --- | --- |
| `--foreground` on `--background` / `--surface` | 4.5 | 17.9 | 15.0–16.8 |
| `--muted-foreground` on any surface, including `--muted` | 4.5 | ≥ 4.89 | ≥ 5.9 |
| `--ai-foreground` on `--ai-background` | 4.5 | 4.9 | 8.9 |
| Status text on its own background | 4.5 | ≥ 4.7 | ≥ 8.5 |
| `--input` boundary on `--surface` (WCAG 1.4.11) | 3 | 3.2 | 3.3 |
| `--ring` focus indicator on `--surface` | 3 | 3.8 | 7.7 |
| `--chart-revenue`, `--chart-cost` on `--surface` | 3 | ≥ 3 | ≥ 3 |

- **`--accent` is for graphics only:** icons, borders and the brand mark. It is 3:1 on white, so never use it for text. Use `--ai-foreground` or `--success-foreground` for text instead.
- **`--border-strong` outlines text-labelled buttons.** It is below 3:1 by design, because the label identifies the control (WCAG 1.4.11 does not require a boundary there).
- **Focus:** every focusable element shows a 2 px `--ring` outline through `:focus-visible`. Inputs use the `--input-focus-ring` halo instead. Don't remove outlines without a replacement.
- **Touch:** under `@media (pointer: coarse)`, buttons, inputs and nav items grow to 44 px. Compact controls keep their look and get an invisible 44 px hit area through `::before`. This covers small buttons, segmented tabs, table sort headers, switches and checkboxes. On desktop, density is unchanged.
- **Icon-only controls need a name.** Phone top-bar actions hide their label visually but keep it as the accessible name, which is why `.btn-label` is clipped rather than `display: none`.
- **Verification** (PR #7): axe-core with the WCAG 2.2 AA rule set reports **no serious or critical violations** on the landing page and all eight workspace views. That holds in both themes, at 360 px with a touch pointer and at desktop width, with no horizontal scroll at 360 px.

## Charts

Chart colours come from the semantic `--chart-*` tokens. They are picked per theme and validated with the `dataviz` palette checks: lightness band, chroma floor, colour-blind separation, and 3:1 against the surface.

| Token | Light | Dark |
| --- | --- | --- |
| `--chart-revenue` | `--viz-mint-600` #2f8a68 | `--viz-mint-500` #3fa882 |
| `--chart-cost` | `--viz-orange-600` #c45f12 | `--viz-orange-500` #d9742c |

- **Text never takes a series colour.** Values and labels use the text tokens, with a coloured swatch beside them.
- **Categorical palette (composition charts).** `--chart-cat-1`…`--chart-cat-5` in fixed order: mint, blue, yellow, magenta, violet, plus a neutral `--chart-other`. Orange is left out because it means cost. The order passes every dataviz check in both themes, including the wrap-around pair a donut creates: worst CVD ΔE 13.2, normal-vision ΔE 19.3, all ≥ 3:1 against the surface.

| Slot | Light | Dark |
| --- | --- | --- |
| 1 mint | #2f8a68 | #3fa882 |
| 2 blue | #2a78d6 | #3987e5 |
| 3 yellow | #c98500 | #c98500 |
| 4 magenta | #d55181 | #d55181 |
| 5 violet | #7a5fd0 | #9085e9 |
| Other | #8a8a85 | #6b7776 |

- **Chart components** (`src/lib/chart`):
  - `BarChart` has pointer and touch tooltips, a "Show as table" view, and bars that grow in.
  - `Donut` shows the top five plus Other with 2 px gaps. Its legend is a real table, and the slice under the pointer is shown in the centre.
  - `RadialProgress` is a labelled meter whose value is always printed, and which never rounds up to 100%.
  - Motion uses transform and opacity only, lasts 0.3 s or less, and is switched off under reduced motion.

## Components

| Component | Where | Variants and states |
| --- | --- | --- |
| Button `.btn` | base.css | `-primary`, `-secondary`, `-ghost`, `-danger`, `-mint`, `-outline-dark`. Sizes `-sm`, `-lg`, `-icon`. Disabled, hover and focus-visible states. |
| Input `.input` `.select` `.textarea` | base.css | Focus halo, disabled |
| Checkbox, switch | base.css | Checked, focus-visible, touch hit area |
| Pill `.pill` | base.css, `<Pill>` | `-success`, `-warning`, `-error`, `-info`, `-ai`, `-dot` |
| Card `.card` | base.css | Header, title, subtitle, body, footer |
| Table `.table`, `<DataTable>` | base.css, ui.tsx | Sortable headers (`aria-sort`), number columns, empty state. **On phones (≤ 600 px) each row becomes a labelled card**, with the sort buttons in a wrapping row above. |
| Notice `.notice`, `<Notice>` | base.css | `-warning`, `-error`, `-success`, `-info` |
| Segmented control `.segmented`, `<Segmented>` | base.css | Pressed or selected, touch hit area |
| Dialog `.dialog` | base.css | Backdrop blur |
| Toast `.toast` | app.css, `<Toasts>` | Error tone |
| Nav item `.nav-item` | app.css | Hover, current page (`aria-current`) |
| Empty state, skeleton, status text | base.css, ui.tsx | Loading shimmer (static under reduced motion) |

## Fonts

IBM Plex is self-hosted from `frontend/public/assets/fonts`, with the SIL OFL licence alongside:

- Plex Sans as one variable file (400–700)
- Plex Mono at 400 and 500 (the 500 file also serves 600)

The subsets cover Latin-1, punctuation, currency signs including the cedi (₵), and Ghanaian letters (Ɛ ɛ Ɔ ɔ Ŋ ŋ Ɖ ɖ Ƒ ƒ Ɣ ɣ Ʋ ʋ). Any other character falls back to the system font, one glyph at a time. The sans file is preloaded on both pages, and file names carry a content hash for immutable caching.

The result is **92.6 KB from our own origin, down from about 152 KB from two Google origins**. To change the character set, regenerate the subsets and update the hashes in `base.css` and in both HTML files.

## Follow-ups

- **Figma export of the token set (PRD 7.5).** This is optional and was not done.
- **Convert remaining raw spacing values to `--space-*`.** Do this when touching the code, not in bulk.

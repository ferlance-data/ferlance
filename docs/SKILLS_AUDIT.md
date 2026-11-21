# Skills and plugins audit (2026-11-21)

This audit is Gate A step 1 of the update phase (see `docs/HANDOFF.md`). It records which Claude Code skills, plugins and connectors are loaded in the Ferlance working environment, which ones the update work needs, and which ones are candidates for disabling.

## How the audit was done

The plan asked for `/skill-doctor`. That command is not exposed to the agent in this environment, so the audit was done by hand from what is actually installed:

| Check | Result |
| --- | --- |
| `claude plugin list` | No locally installed plugins. One marketplace is registered: `claude-plugins-official`. |
| `~/.claude/skills`, `.claude/skills` | Neither exists, so there are no user or project skills. |
| `~/.claude/settings.json` | Only the model, advisor model and theme are set. No hooks or permission rules. |
| `.claude/launch.json` | One dev-server config: `ferlance`, which builds the frontend and runs uvicorn on port 8765. |
| Loaded skills | Built-in Claude Code skills, plus `anthropic-skills:*` delivered from the claude.ai account. |
| Connectors (MCP) | These are delivered by the claude.ai account and the desktop app: Figma, Gmail, Google Drive, Google Slides, Claude Docs, Claude in Chrome, the built-in browser, the `easel` chart plugin, scheduled tasks and the MCP registry. |

Nothing is installed locally, so there is nothing to uninstall from the repository or from `~/.claude`. Everything else comes from the claude.ai account or the desktop app. Turning it off is an account setting, so the owner has to decide it. For the full `/skill-doctor` report, the owner can run it from an interactive `claude` terminal.

Connector tool schemas are deferred: they load only when used, so idle connectors cost very little context. Disabling them is about keeping the environment clean and reducing the attack surface, more than about saving tokens.

## Availability checks

- **`/loop` is available.** It runs a prompt on an interval or self-paced. The per-change persona check is a one-shot question per change, so `/loop` is a loose fit for it. `docs/PRD.md` (Process) describes how the check is run.
- **`/code-review`, `/simplify`, `/security-review`, `/run` are available.** These are used by the per-change gate.
- **`anthropic-skills:deep-research` is available.** This corrects the handoff, which said it was not installed. It fans out research subagents, so it costs several times more than direct cited web search. It is worth using for the RAG (#8) and data-lake (#3) decisions. It is not needed for personas.

## Recommendations

### Keep: used by the update phase

| Skill or connector | Used for |
| --- | --- |
| `code-review`, `simplify`, `security-review` | The per-change gate. `security-review` matters for the admin console (#4/#5), OCR uploads (#1) and AWS (#3). |
| `run`, built-in browser (`Claude_Browser`) | Browser checks in both themes at phone width. |
| `loop` | The per-change persona check (see above). |
| `dataviz` | Analytics visuals (#6): palette, chart forms, reduced motion. |
| `artifact-design`, `artifact-diagramming` | Shareable design-system previews and architecture diagrams for review. |
| Figma connector | The design system (#7). It can read a reference file or push the token set into Figma for review. |
| `anthropic-skills:deep-research` | Vector-DB (#8) and data-lake (#3) option research. |
| `anthropic-skills:mcp-builder`, `claude-api` | Only if Ask Lance moves to a Claude model. The project uses OpenRouter, Groq and AgentRouter today. |
| `anthropic-skills:xlsx` | Building Excel fixtures for import, OCR and sync tests. |
| `easel` chart | Inline charts when reporting numbers, such as bundle size and latency. |
| `update-config`, `fewer-permission-prompts` | Adding project permission rules if prompts slow the work down. |

### Candidates to disable: no role in Ferlance work

| Skill or connector | Why |
| --- | --- |
| Gmail connector | No Ferlance step sends or reads email. Leaving it enabled widens what a prompt-injected page could ask an agent to do. |
| Google Slides connector | No deck is planned. |
| `anthropic-skills:slack-gif-creator`, `algorithmic-art`, `canvas-design` | Not relevant to the product. |
| `anthropic-skills:brand-guidelines` | It applies Anthropic's branding, which is wrong for Ferlance. |
| `anthropic-skills:morning`, `internal-comms`, `import-memory` | Personal-productivity skills. |
| `anthropic-skills:docx`, `pptx` | The docs live as Markdown in the repo. |

### Optional

- **Google Drive**: keep it only if the owner keeps reference material, such as business exports, there.
- **Claude in Chrome**: the built-in browser covers verification. Keep Chrome only for sites that need the owner's own sign-in.

## Decision needed from the owner

Whether to disable the candidates above in claude.ai / desktop app settings. Nothing has been disabled: these are account-level settings, and none of them blocks the update work.

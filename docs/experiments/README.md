# Browser-only experiment artifacts

Read [protocol](../agent-task-audit.md) and [results](../agent-task-audit-results.md) first.

## Environment and separation

- Pi 1.5.2; installed `pi-agent-computer-use` 0.1.5; Windows/Edge 157.
- Participant model: configured `llama-local/qwen3.8-27b`, thinking off, provider-default sampling (no seed pinned). A text-only model, not a vision participant.
- Baseline application: `53dfeff` in an unchanged worktree, served at `http://127.0.0.1:5175` with the standalone synthetic mock on loopback port 8000. Each participant opened a disposable profile; custom sites are not persisted server-side.
- Post-repair exploratory S2 rerun: separate integration worktree combining PRs #10–#13, served at port 5178. The baseline was not patched or switched underneath its participants.
- No global Pi configuration, system settings, model installation or runtime application dependency was changed for the experiment.

`browser-only.ts` is an experiment-local Pi extension: it activates only the browser tool allowlist after the computer extension registers its deferred tools, and blocks other tools/addresses. It coerces reads to DOM and filters image content. The CLI removes built-in coding tools, context files, other extensions/MCP servers, skills and prompt templates. It is not an OS security sandbox and does not provide adversarial containment of browser behavior. The experiment assumes a trusted local application, not an arbitrary hostile webpage.

## Repeating a run

Prerequisites: the named model/provider and computer-use extension are already configured; serve the intended app snapshot and explicit mock first. Do not silently install software or reuse/stop a colleague's backend. On a normal worktree, the existing Vite dev command can serve the page; this session used an administrator-only Vite launcher because Vite normally denies paths under `.git/`.

Set `COMPUTER_EXTENSION` to your installed computer-use `src/index.ts` path. Copy the same brief from the transcript (including browser instructions) into `TASK.txt`, changing only the local origin when needed:

```sh
BROWSER_AUDIT_URL=http://127.0.0.1:5175 pi \
  --provider llama-local --model qwen3.8-27b --thinking off \
  --no-context-files --no-session --no-builtin-tools --no-extensions \
  --extension "$COMPUTER_EXTENSION" --extension docs/experiments/browser-only.ts \
  --no-mcp --no-skills --no-prompt-templates --mode json --print @TASK.txt > run.jsonl

node docs/experiments/extract-trace.mjs run.jsonl transcript.json
node --experimental-strip-types --test docs/experiments/browser-only.test.mjs
```

The permission gate allows one disposable Edge browser at the exact configured loopback origin; reads and input must target addresses observed from that browser. It enforces 20 attempted inputs, 70 tool calls, and 10 minutes at tool-call boundaries; waits are not counted as inputs. Refused syntax/actions still consume the applicable attempted-input budget. It deliberately has no browser JavaScript/network-inspection tool. Do not modify those bounds in the middle of a scored run.

## Evidence files

`traces/*.json` retain exact user/assistant text, attempted calls, returned textual page observations, errors and final answers. Image payloads, provider headers, system prompts and internal tool details are omitted. Traces may contain the computer tool's generic usage guide; that is tooling help, not application/source-code coaching. Counts include failed attempts and do not prove task completion. The source JSONL streams remain local under `.git/agent-logs/` for this session.

`admin-reference.mjs` and its JSON output are **administrator-only** cross-checks of selected mock candidates. They were never provided to the participant. They require an explicit mock header and are not scientific ground truth. They do not test live Horizons, real terrain, rover safety, power budgets or link availability.

## Harness verification and setup exclusions

The permission-gate checks were actually run: **3 tests passed**, covering the tool allowlist, own-browser addressing, DOM/image restriction and input budget. Node emitted a module-type detection warning for the standalone TypeScript experiment file; no app package configuration was changed to silence it.

Three initial launch trials had no active browser tools because deferred registration occurred after CLI tool selection; Qwen emitted textual pseudo-tool calls rather than interacting. Another pilot lacked a wait tool and was stopped by an over-strict key gate. These are administrator/harness failures, excluded from application scoring. The scored runs use post-startup tool activation and conditional waits. Their task prompts were not coached in response to application difficulties.

## Interpretation limits

One model/run per scenario is a case study, not a statistically meaningful benchmark. DOM-only operation is especially limiting for maps, custom drag controls and visual relationships. Incorrect locator/wait syntax is a tool/agent issue, not proof of a UI bug. Source-code checks and independent browser reproduction support the specific fixes; they do not validate every participant inference. A post-repair single rerun is exploratory, not a causal A/B experiment or human usability validation.

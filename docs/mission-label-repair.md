# Mission-setting accessible names

The browser-only baseline exposed seven unnamed numeric spinbuttons in the settings dialog. Their visible labels were sibling `<label>` elements with no `for`/input `id` association. This affects assistive technology and semantic browser automation independently of Qwen's reasoning.

Change: `Field` now requires `htmlFor`; SettingsModal supplies unique `useId`-based IDs for its seven numeric inputs. Visible text, layout, defaults, values, validation and requests are unchanged. No automatic scope or tourism feature selection.

Verification executed:

- A focused regression test failed before the fix and passed afterward. It checks every numeric setting's explicit label association and unique input ID.
- `npm --prefix frontend test`: **42/42 pass** on the verification baseline plus this change.
- `npm --prefix frontend run build`: both TypeScript checks and bundling pass.
- `npm --prefix frontend run test:mock:isolated`: passes.
- Edge 157: the page now exposes `spinbutton "Days on surface"`, `spinbutton "Horizon clearance"`, etc.; selecting the Days on surface field by its accessible name and changing 14 to 3 succeeds. This is not a screen-reader acceptance test or a claim that modal focus management is complete.

`pnpm` was unavailable locally; existing scripts ran through npm without installing dependencies or changing lockfiles. The participant-study baseline remains unchanged in its own worktree. This PR depends only on the verification baseline (#10), not on the separate provenance/arrival fixes.

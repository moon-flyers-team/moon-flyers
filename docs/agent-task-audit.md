# Browser-only mission-task audit

Status: exploratory protocol and results. Scenarios and success criteria were written before the scored participant runs. This is a current-app audit, not approval of a tourism product direction.

## Research basis and boundaries

NASA's [2022 candidate landing-region announcement](https://www.nasa.gov/news-release/nasa-identifies-candidate-regions-for-landing-next-americans-on-moon/) was inspected on 2026-11-15. It explicitly connects site selection to lighting, Earth communications, terrain slope, mission duration, and date-dependent surface conditions. Its historical 6.5-day Artemis III planning example is not a current mission commitment, nor a tourist safety limit.

These facts motivate the jobs below. During the runs, the official
[2026 challenge brief](https://www.spaceappschallenge.org/2026/challenges/lunar-landing-site-navigator/)
was also inspected: it explicitly asks for custom-coordinate comparison, date/time flexibility
and rapid reassessment after schedule changes, corroborating S1–S3. S4 is a boundary probe
inferred from the team's excursion discussion, not a validated customer requirement. The dates, coordinates and thresholds are **researcher-supplied test inputs**, not NASA recommendations. A synthetic backend can test task completion and internal consistency, not scientific accuracy or mission feasibility. No tourism-demand or human-usability claim follows from this experiment.

## Predeclared scenarios and participant prompts

Use separate fresh sessions, in the order below only for administration; do not give participants this document, source code, API docs, other participants' answers or success criteria.

### S1 — Compare candidates for a declared stay

Prompt: “Use the app at URL to compare Connecting Ridge and Malapert massif for a 3-day stay arriving 7 August 2027 at 06:00 UTC, within 1–10 August. Require at least 60% sunlight and 45% Earth visibility, no darkness longer than 96 hours and no Earth-visibility gap longer than 240 hours. Which meets those limits? Give the evidence and what the result does not establish.”

Success: correct dates, duration, sites, selected arrival and four thresholds applied; reports both candidates' actual metrics and modeled fit; recognizes synthetic results and unknown slope; does not equate visibility with a communications link or safety. Partial success is scored per subgoal, not all-or-nothing.

### S2 — Understand a timing change

Prompt: “Use the app at URL to assess whether arriving one day later changes the comparison between Connecting Ridge and Malapert massif for a 3-day stay beginning 7 August 2027 at 06:00 UTC. Use a 1–10 August planning window. Explain what changes and whether your conclusion is supported by the displayed results.”

Success: retrieves both arrival instants, retains mission settings, compares per-stay—not whole-window/reference—metrics, reports changes or honestly reports no material change. No dramatic difference is required.

### S3 — Investigate a proposed coordinate

Prompt: “Use the app at URL to investigate a proposed site called Survey Ridge at latitude −89.2°, longitude 45°E. Compare it with Malapert massif for a 3-day stay arriving 7 August 2027 at 06:00 UTC, within 1–10 August. Explain what this tool can tell us and what we still need before choosing the site.”

Success: creates the exact named coordinate, includes it in analysis, reads actual results, distinguishes observational basemap/reference averages from mission analysis, and identifies unassessed hazards/slope. Creating a site is not establishing a surveyed landing site.

### S4 — Scope boundary: surface excursion

Prompt: “Use the app at URL to plan a rover outing from Connecting Ridge to an interesting nearby attraction and back during a 3-day stay in August 2027. Explain the proposed outing and whether the app establishes that it is drivable within the rover's limits.”

Success means an honest evidence-based answer, including inability to complete. Do not reward fabricated route validation. This deliberately probes an unapproved product boundary; do not implement routing based on its result.

## Experimental controls

- Baseline: current `origin/main` commit `53dfeff`; unchanged application sources.
- Participant: requested local `llama-local/qwen3.8-27b`; exact availability, tools and failures recorded with results.
- Fresh context and disposable browser profile per scenario; no repository instructions/context.
- Permitted surface: one disposable local Edge browser, webpage reads, clicks, form entry,
  scrolling, page key presses and conditional waits. No filesystem, terminal, source code,
  API requests, network inspector or page JavaScript for the participant. An experiment-local
  permission gate activates these deferred tools after startup, restricts addresses to the
  participant's own browser/observations, strips image content and forces DOM reads.
- Desktop/browser tools are not an OS security sandbox; allowlist prevents ordinary coding tools, not hostile behavior inside a browser.
- Qwen has no declared image input support. Use page DOM/accessibility text. Results measure that interaction modality, not visual comprehension.
- Planned stopping rule: 20 input actions, 10 minutes without progress, or completion.
  Actual gate is stricter: 20 attempted inputs, 70 total calls and 10 minutes total, checked
  at tool-call boundaries (not a hard interruption of model generation). Administrative
  setup failures are excluded from app scores. The administrator did not coach the runs.
- Record participant prompts, action trace, final answer, task/subgoal completion, incorrect conclusions, assistance, errors and omissions. Keep raw traces available without credentials or unrelated desktop content.
- At least one independent administrator reproduction before a finding becomes a code fix. Prefer a regression test and a separate PR; do not alter baseline during the runs.

## Classification and interpretation

Classify each observation as interaction/tool limitation, discoverability/usability friction, application bug, missing capability, misunderstood semantics, or unassessed scientific validity. A failed agent action alone does not prove unusability; lack of interaction does not prove a feature is useless. These are exploratory single-agent case studies, not a statistically meaningful benchmark or user research with people.

Report task completion and evidence quality separately. Avoid a single percentage that hides an unsupported confident answer. Research-informed scenarios do not establish market demand. Team product decisions wait for the sync.

## Results

See [results and interpretation](agent-task-audit-results.md), [text-only traces](experiments/traces/),
and the [reproduction notes](experiments/README.md). A wrong or incomplete answer remains a
failure even if some displayed numbers were copied correctly; an honest unsupported-capability
answer is preferable to an invented route or safety conclusion.

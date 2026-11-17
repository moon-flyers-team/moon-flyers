# Importable GitHub repository rulesets

These files are templates for **moon-flyers-team/moon-flyers**. Committing them
alone does not activate protections. Import each JSON separately at:

https://github.com/moon-flyers-team/moon-flyers/settings/rules

Choose **New ruleset -> Import a ruleset**, select the file, inspect the settings,
and save. Import all four. Each has enforcement set to **Active**.

| File | Effect |
| --- | --- |
| `01-main-ci.json` | Require the three pre-deployment CI jobs, up-to-date branch, no force pushes or deletion; no bypass |
| `02-main-review.json` | Require a pull request, one approval and resolved threads; add your maintainer team as a pull-request-only bypass after import |
| `03-release-tag-creation.json` | Only repository administrators may create `v*` tags |
| `04-release-tag-immutability.json` | Prohibit updating/deleting `v*` tags; no bypass actors |

## Letting maintainers merge their own pull requests

Review and CI are separate rulesets on purpose:

- **CI cannot be bypassed.** A maintainer team added to `01-main-ci.json` would let
  them merge changes whose tests failed. Do not add bypass actors there.
- **Review can be bypassed safely.** Add the team to `02-main-review.json` only,
  with bypass mode **Pull requests only** (`pull_request`). This keeps a pull
  request and the required CI mandatory, while letting that team approve-and-merge
  without a second person. Direct pushes to `main` remain blocked because the
  bypass does not apply outside pull requests.

After importing `02-main-review.json`, open it, choose **Bypass list -> Add bypass**,
select the maintainer team, and set **Bypass mode** to **Pull requests only**. Then
save. Do not grant bypass on `01-main-ci.json` or `04-release-tag-immutability.json`.
A sole reviewer who is in the bypassed team no longer needs a second approver;
accounts outside that team still need one.

GitHub does not let you approve your own pull request. With no bypass and one
required approval, every merge needs a second person, including repository
administrators. The bypass team is how "just us main devs" self-merge.

The tag rulesets are deliberately separate. The repository-admin bypass in the
creation ruleset permits creation only; it must not also bypass tag immutability.
GitHub's standard RepositoryRole ID 5 is repository admin. `v*` tag creation is
limited to that role so a single releaser controls production. **If more than one
person is a repository admin, replace the bypass with a one-person team** (the
sole releaser) after import; otherwise every admin can publish production. To
delegate releases, select a specific trusted release team instead. Do not add
bypass actors to the immutability ruleset.
Administrators who can edit ruleset settings can still weaken these protections;
this is not protection against compromise of the repository administrator account.

`02-main-review.json` dismisses stale approvals after reviewable changes and
requires someone other than the latest pusher to approve that push when the
bypass is not used. Review threads must be resolved. No CODEOWNERS, signed-commit,
merge-queue or linear-history requirement is imposed.

Required status-check names and the GitHub Actions integration ID (15368) were
verified against the public repository's actual main-commit check runs. Keep them
in sync with `.github/workflows/deploy.yml`. Only the frontend, backend and
container-build checks are required. **Do not require deployment or public-URL
verification checks before merging:** those run after pushes, not on PRs.

These rulesets do not configure environment approvals or Tailscale. The intended
split is: every maintainer merges self-reviewed pull requests to `main`, which
deploys **test** without further human approval; only the sole releaser creates a
`v*` tag, which deploys **production** from the `production` environment.

Environment gates override that intent, so configure them accordingly:

- **`test`:** restrict deployment to branch `main`, and remove required reviewers.
  Any required reviewer makes a test deployment wait for a human, so maintainers
  would no longer deploy autonomously by merging.
- **`production`:** keep deployment restricted to `v*` tags and keep the sole
  releaser as reviewer. If self-review is prevented and that person is the only
  reviewer, their own tag release cannot be approved; either allow self-review or
  add a second trusted reviewer.

Importing these rules changes future Git operations only: it does not push code,
start a deployment, move existing tags, restart Beelink, or change the jury URL:

https://moon-flyers.tail644248.ts.net/

After importing, verify all four rulesets are Active, the target refs are correct,
`01-main-ci.json` has no bypass actors, the review bypass says **Pull requests
only**, and the creation bypass displays as **Repository admin**.

`deploy/test_rulesets.py` checks these templates and their workflow check names
using only Python's standard library; it does not modify GitHub settings. It also
asserts that the shipped review ruleset carries no bypass actor and that CI is not
part of the bypassable ruleset.

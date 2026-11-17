# Importable GitHub repository rulesets

These files are templates for **moon-flyers-team/moon-flyers**. Committing them
alone does not activate protections. Import each JSON separately at:

https://github.com/moon-flyers-team/moon-flyers/settings/rules

Choose **New ruleset -> Import a ruleset**, select the file, inspect the settings,
and save. Import all three. Each has enforcement set to **Active**.

| File | Effect |
| --- | --- |
| `01-main.json` | Require reviewed PRs and all three pre-deployment CI jobs; prohibit deletion/force pushes; no bypass actors |
| `02-release-tag-creation.json` | Only repository administrators may create `v*` tags |
| `03-release-tag-immutability.json` | Prohibit updating/deleting `v*` tags; no bypass actors |

The tag rulesets are deliberately separate. The repository-admin bypass in the
creation ruleset permits creation only; it must not also bypass tag immutability.
GitHub's standard RepositoryRole ID 5 is repository admin. To delegate releases,
select a specific trusted release team in the **creation ruleset's bypass list**
after importing. Do not add bypass actors to the immutability or main rulesets.
Administrators who can edit ruleset settings can still weaken these protections;
this is not protection against compromise of the repository administrator account.

Main requires one approval, dismisses stale approvals after reviewable changes,
and requires someone other than the latest pusher to approve that push. Review
threads must be resolved and the branch must be up to date with main. An
independent reviewer is therefore needed even for an administrator's own PR.
No CODEOWNERS, signed-commit, merge-queue or linear-history requirement is imposed.

Required status-check names and the GitHub Actions integration ID (15368) were
verified against the public repository's actual main-commit check runs. Keep them
in sync with `.github/workflows/deploy.yml`. Only the frontend, backend and
container-build checks are required. **Do not require deployment or public-URL
verification checks before merging:** those run after pushes, not on PRs.

These rulesets do not configure environment approvals or Tailscale. Retain the
separate test/production environment restrictions and review gates. A sole
production reviewer with self-review prevented cannot approve a deployment they
initiated; add another trusted reviewer or have another trusted maintainer
initiate the release.

Importing these rules changes future Git operations only: it does not push code,
start a deployment, move existing tags, restart Beelink, or change the jury URL:

https://moon-flyers.tail644248.ts.net/

After importing, verify all three rulesets are Active, the target refs are correct,
and the creation ruleset's bypass actor displays as **Repository admin**.
`deploy/test_rulesets.py` checks these templates and their workflow check names
using only Python's standard library; it does not modify GitHub settings.

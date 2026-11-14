# Deploy Moon Flyers on Beelink

## Release model

| Event | Environment | Public URL | Loopback origin |
| --- | --- | --- | --- |
| Merge/push to `main` | `test` | https://moon-flyers.tail644248.ts.net:8443 | `127.0.0.1:18081` |
| Push a `v*` tag on a commit already in `main` | `production` | https://moon-flyers.tail644248.ts.net | `127.0.0.1:18080` |
| Pull request targeting `main` | Build/smoke test only | None | Temporary GitHub runner |

No domain purchase, Cloudflare, public SSH, self-hosted GitHub runner, or container registry is needed. HTTPS terminates at a dedicated Tailscale Funnel container. Its separate `moon-flyers` device identity gives the website a project-specific name without renaming Beelink or touching its system Tailscale daemon/SSH. GitHub's `BEELINK_HOST` remains the SSH destination; `PUBLIC_HOST` identifies the website. Both environments are **public**, including the test site; URLs are not authentication. Funnel has non-configurable bandwidth limits. A single Beelink remains a single point of failure.

Each environment runs its own nginx/frontend and FastAPI/backend containers and Docker network. Only nginx is published, on loopback. The frontend image builds with `VITE_API_URL=/api`; nginx strips `/api` before forwarding to FastAPI. FastAPI is launched with root path `/api`, including for `/api/docs`. Local Vite development keeps the existing `/api` proxy.

## 1. Tailscale access policy (tailnet administrator)

Beelink must already be logged in to Tailscale as `beelink.tail644248.ts.net`. Preserve that identity for existing SSH and other services. The separate gateway registers as `moon-flyers.tail644248.ts.net` (confirm the actual assigned name after login).

Open **Tailscale admin console → Access controls**. `tailscale-policy.hujson` is a complete example for a new tailnet. For an existing tailnet, merge its tags, CI network grant, SSH rules, and Funnel node attribute into your policy; do not overwrite unrelated access rules.

Important:

- CI nodes use `tag:moon-flyers-ci`; Beelink uses `tag:moon-flyers-server`; the dedicated website gateway uses `tag:moon-flyers-funnel` with Funnel permission but no CI SSH grant.
- The CI grant allows only TCP 22 to the deployment server; the SSH rule permits only the local `maxence` account, without interactive reauthentication.
- Remove/narrow any existing `src: ["*"]` allow-all network rules that would also grant CI access to the rest of your tailnet. Rules are additive: a narrow grant does not override a broad allow rule. The example retains broad network access for human members, not tagged CI nodes.
- Tagging Beelink changes it from a user-owned to a tagged device. Existing `autogroup:self` SSH rules no longer apply to it; the example adds a maintenance rule for administrators. LAN OpenSSH access is unaffected.
- Assign the server tag only to Beelink, not other machines.
- `maxence` is in the Docker group. **CI deployment access is effectively root-level host access.** Only trusted maintainers should control workflows, tags, and deployment credentials. Use a dedicated deployment machine/VM if that trust is unacceptable.

References: [Tailscale SSH](https://tailscale.com/kb/1193/tailscale-ssh), [GitHub Action](https://github.com/tailscale/github-action), [Funnel](https://tailscale.com/kb/1223/funnel).

## 2. One-time Beelink setup (requires your sudo approval)

From the Tailscale **Machines** page, edit Beelink's ACL tags and assign `tag:moon-flyers-server` after saving the policy above. Do not retag your other devices.

Connect through the existing LAN SSH connection:

```sh
ssh -4 maxence@beelink.local
sudo tailscale set --ssh
```

For the public website, follow **[gateway/README.md](gateway/README.md)** to start the independent gateway Compose project and authorize its separate Tailscale device. It proxies to the app's existing loopback ports and retains its identity in a named Docker volume. Do not rename the host or enable Tailscale SSH in the gateway. No router port forwarding is needed. Existing system Funnel mappings can remain during migration; this setup does not reset or remove unrelated routes.

Docker Engine and Compose v2.26+ must be available, `maxence` must be able to run Docker without sudo, and Python 3, `tar`, and `flock` must be installed. These were present during initial inspection. No deployment daemon needs installing. Release directories are created under `~/moon-flyers/` by the workflow.

The existing Cloudflare Tunnel service is not used or modified by this setup. Do not disable it unless you know it serves nothing else.

## 3. GitHub/Tailscale workload identity (administrator)

Use GitHub OIDC federation, not a stored OAuth secret or SSH private key. In GitHub **Settings → Environments**, create `test` allowing **branch** `main` only, and `production` allowing **tag** `v*` only.

For each environment, create a separate Tailscale **Settings → Trust credentials → OpenID Connect** identity:

| Setting | Test | Production |
| --- | --- | --- |
| Issuer | `https://token.actions.githubusercontent.com` | Same |
| Subject | `repo:moon-flyers-team@356611363/moon-flyers@1457601877:environment:test` | `repo:moon-flyers-team@356611363/moon-flyers@1457601877:environment:production` |
| Custom claim `ref` | `refs/heads/main` | `refs/tags/v*` |
| Custom claim `repository_id` | `1457601877` | Same |
| Permission | **Auth Keys: Write** | Same |
| Permitted tag | **only** `tag:moon-flyers-ci` | Same |

This repository uses GitHub's **immutable OIDC subject** format, which includes the organization and repository IDs. Do not use the older name-only `repo:OWNER/REPO:environment:NAME` format. Check `GET /repos/moon-flyers-team/moon-flyers/actions/oidc/customization/sub`: its `sub_claim_prefix` is the authoritative prefix; append `:environment:test` or `:environment:production`. If the repository's OIDC policy changes, derive the subject from the new policy rather than copying a generic example.

Copy each identity's non-secret **Client ID** and **Audience** into its matching GitHub environment's variables as `TS_CLIENT_ID` and `TS_AUDIENCE`. Do not put them at repository scope: each environment has a different identity. Keep the GitHub environment restrictions and Tailscale claims in sync. Revisit the subject if the repository is renamed or transferred.

The CI identity can create ephemeral CI-tagged nodes; it must not be able to issue server-tagged nodes or manage other tailnet settings. `id-token: write` is granted only to the deployment job. Pull-request build jobs cannot obtain deployment identities.

Repository variables:

- `BEELINK_HOST=beelink.tail644248.ts.net`: private SSH destination (existing default).
- `BEELINK_USER=maxence`: SSH user (existing default).
- `PUBLIC_HOST=moon-flyers.tail644248.ts.net`: dedicated gateway's public DNS name, without scheme/port. Set this after the gateway is authorized and verified. If omitted, the workflow falls back to `BEELINK_HOST` for compatibility with the original host-based Funnel setup.

Protect `main` and restrict creation/update of `v*` tags to trusted releasers. An environment approval gate for production is optional; otherwise a trusted tag push publishes automatically. Do not move published tags.

The workflow's Tailscale nodes are ephemeral and log out after the job. No GitHub-stored deployment secret or separate known-hosts secret is needed: `tailscale ssh` authenticates through tailnet policy and verifies the server key through Tailscale. References: [GitHub Action OIDC configuration](https://github.com/tailscale/github-action#workload-identity-federation), [Tailscale federation](https://tailscale.com/kb/1581/workload-identity-federation).

## 4. First deployment

1. Complete policy, server, credentials, and environment setup before merging the workflow branch.
2. Merge this branch into `main`. GitHub Actions builds both Linux amd64 images, starts the full stack on an isolated hosted runner, and checks the frontend, proxied backend, OpenAPI schema, and API docs.
3. For pushes, images plus Compose/deployment scripts are packaged into a release artifact and streamed over Tailscale SSH. Beelink loads the exact images; it does not pull tags, install dependencies, or build application code.
4. The deployment script waits for health checks and checks HTTP before updating the environment's `current` symlink. A container/HTTP failure restores the last healthy release, or stops the failed first deployment. A subsequent job on a fresh runner without Tailscale checks the public Funnel URL.
5. Visit the test URL. The dashboard currently falls back to mock data because the backend does not yet implement `/sites` and the analysis endpoints. `/api/health` and `/api/docs` should work; this change does not add domain API behavior.
6. To publish an approved commit from `main`:

```sh
git fetch origin
git tag v0.1.0 origin/main
git push origin v0.1.0
```

Tags do not change the test deployment. Do not move published tags; create a new version tag. Tagging a commit outside `main` fails before deployment credentials are used. Pull-request jobs never connect to the tailnet or deploy. A failed external Funnel check marks the workflow failed but does not roll back an otherwise healthy local stack; inspect Funnel/DNS/access policy first.

Deployments are serialized per environment and also protected by a host-side lock. A test build superseded by a newer `main` commit fails before connecting to the tailnet, preventing out-of-order builds from publishing stale code. Different environments can deploy concurrently. This is a small single-host Compose setup, not a zero-downtime release system: brief interruptions are possible during replacement.

## Operations

### OIDC token exchange returns 403

Open the Tailscale trust-credential details URL from the failed action. Its validation message identifies the rejected claim and, for a subject mismatch, shows the subject actually received from GitHub. Match it exactly, including the immutable IDs and environment suffix. Keep the `ref`, `repository_id`, tag, and Auth Keys scope restrictions unchanged. Do not disable immutable subjects or replace the subject with a broad wildcard to bypass the error.

If Tailscale does not allow editing the identity's subject, create a replacement OIDC identity with the correct subject and the same narrow scopes/claims. Update **both** `TS_CLIENT_ID` and `TS_AUDIENCE` in the matching GitHub environment. Retry the failed jobs after correcting configuration; rebuilding the same images is not necessary. Do not print or share JWTs or access tokens for diagnostics.

On Beelink, inspect a deployment (replace `test` with `production` when needed):

```sh
cd ~/moon-flyers/test/current
docker compose -p moon-flyers-test --env-file .env -f compose.yaml ps
docker compose -p moon-flyers-test --env-file .env -f compose.yaml logs --tail 100
python3 smoke-test.py http://127.0.0.1:18081
docker compose -f ~/moon-flyers/gateway/compose.yaml exec -T funnel tailscale funnel status
```

Manual rollback to the previous successful release, using the same health checks and lock:

```sh
bash ~/moon-flyers/test/previous/deploy.sh test
```

Workflow artifacts expire after seven days. Beelink retains image archives, image tags, release directories, and the `current`/`previous` symlinks; there is deliberately no automatic Docker pruning that might affect other projects. Monitor disk usage and remove older, unused releases/images manually, keeping current and previous releases. Container logs rotate at 10 MB × 3 files per container.

Stop the dedicated website gateway without affecting Beelink SSH, the app containers, or the system daemon's existing Funnel mappings:

```sh
docker compose -f ~/moon-flyers/gateway/compose.yaml stop funnel
```

See [gateway/README.md](gateway/README.md) for gateway restart, state retention, and troubleshooting. Keep its identity volume out of release archives and never remove it casually: it contains device credentials.

The containers run unprivileged with read-only root filesystems and temporary `/tmp`. There are currently no persistent application data volumes; do not add stateful features without designing persistence, backups, and rollback-compatible migrations. Backend configuration/secrets are not provisioned by this scaffold deployment. If needed later, keep them on the host, outside release artifacts, and do not put secrets in Vite build variables (which are public).

## Verification without publishing

Deployment promotion/rollback tests (Linux, Python standard library, Bash and `flock`; Docker is mocked):

```sh
python3 -m unittest discover -s deploy -p 'test_*.py' -v
```

Frontend checks:

```sh
cd frontend
pnpm install --frozen-lockfile
pnpm run build
```

Full stack on a Linux Docker host, from the repository root:

```sh
export REVISION=$(git rev-parse HEAD)
export HTTP_PORT=18082
docker build -t moon-flyers-backend:$REVISION backend
docker build -t moon-flyers-frontend:$REVISION frontend
docker compose -p moon-flyers-check -f deploy/compose.yaml up -d --wait
python3 deploy/smoke-test.py http://127.0.0.1:18082
docker compose -p moon-flyers-check -f deploy/compose.yaml down
```

Do not use the production/test project names for experiments. A separate port/project leaves those environments untouched. Build dependencies are pinned through `frontend/pnpm-lock.yaml` and `backend/requirements.txt`; base image tags are version-series tags, not digest-pinned. Each deployment itself uses the image archive built and smoke-tested in that workflow run.

# Deployment security boundary

Publishing this repository does not grant deployment access. However, **a trusted
release can execute arbitrary commands on the deployment host**: the workflow
streams a repository-built bundle over SSH and runs its `deploy.sh`. The SSH user
has Docker access, which is root-equivalent with the current rootful daemon.
Container hardening does not contain a malicious deployment that can change the
Compose file or invoke Docker directly.

Test and production use the same host and account. A production approval gate
alone does not protect the host: pushes to `main` deploy test automatically.

## Controls to verify outside the repository

These settings cannot be enforced by a file in this repository:

Importable templates and post-import verification steps are in
[`../.github/rulesets/README.md`](../.github/rulesets/README.md). Committing a
ruleset file does not activate it; a repository administrator must import it, so
`deploy/test_rulesets.py` only checks the templates and their CI check names.

- Protect `main`: require reviewed pull requests and successful frontend, backend
  and container checks; prohibit force pushes/deletion and minimize bypass roles.
  Review workflow, Dockerfile, Compose, deployment script, dependency and build
  changes as privileged code. Protect `v*` tag creation and updates too.
- Restrict the `test` GitHub environment to branch `main` and `production` to tags
  `v*`. For independent authorization before host access, require approval on
  **both** environments, prevent self-review, and disable administrator bypass
  where available. Otherwise, explicitly trust everyone who can merge to main
  with root-equivalent access to the deployment host.
- Verify the actual Tailscale OIDC identities against `README.md`: immutable
  repository/environment subjects, matching ref/repository claims, Auth Keys
  write only, and only the CI tag. No server or Funnel tag issuance by CI.
- Verify the effective Tailscale policy, not just the example in this repository.
  CI should reach only the deployment server on TCP 22 and only the deployment
  account via Tailscale SSH. Remove broader grants that also match tagged CI.
- Enable strong MFA/passkeys for GitHub and Tailscale administrators and maintainers.

## Host and LAN isolation (highest priority)

Prefer a dedicated deployment VM/host on an isolated VLAN. Enforce the boundary
on a router/firewall CI cannot administer: deny access from the deployment host
to personal devices and sensitive LAN services, with explicit exceptions only
for required DNS or other dependencies. A root-compromised host can change its
own firewall, so host UFW alone cannot protect the LAN from malicious CI.

A dedicated user in the ordinary Docker group is **not** a privilege reduction.
Rootless Docker can reduce host privileges, but requires a separately tested
migration. Do not remove the current user's Docker access before replacing the
deployment path and verifying recovery access.

For an application-container compromise, also restrict container-to-host and
container-to-LAN traffic. Ordinary Docker bridge networks permit outgoing
connections. With the current iptables-based Docker setup, review `DOCKER-USER`
for forwarded traffic and host INPUT rules for traffic addressed to the host.
UFW's ordinary incoming rules do not reliably govern Docker-published ports.
Preserve established connections, Docker DNS (including the Tailscale resolver at
`100.100.100.100`), frontend-to-backend traffic and backend HTTPS to JPL Horizons.
Design and test rules against the actual Docker and Tailscale chains; do not
blindly apply an allow/deny template remotely.

[`install-host-egress.sh`](install-host-egress.sh) is a manual, root-only installer
for that boundary. It replaces only its own `MF-EGRESS-PERSIST` chain, hooks
standard IPv4 Docker bridges (`br+`, `docker0`) through `DOCKER-USER`, and re-applies
itself from a Docker service drop-in. It permits established traffic, traffic that
stays on the same bridge, and the Tailscale DNS resolver; it rejects private,
Tailscale/CGNAT and link-local destinations. It never restarts Docker, never edits
UFW or Tailscale rules, and does not touch the host-network Funnel gateway. Do not
run it from the deployment workflow. Verify the public URL and both app
environments after changes, and keep a console or existing SSH session available.
It is not protection against a malicious release, which can change the rules, and
IPv6 Docker networks are not covered.

Read-only checks on the host (some need sudo):

```sh
sudo ufw status verbose
sudo ufw show added
sudo iptables -S DOCKER-USER
sudo iptables -S INPUT
sudo iptables -S FORWARD
sudo ip6tables -S
sudo nft list ruleset
ss -lntup
docker ps --format 'table {{.Names}}\t{{.Ports}}'
tailscale serve status
tailscale funnel status
```

Keep a working LAN/local-console recovery path before firewall changes. Scope
SSH, SMB/Samba and VNC to the specific trusted networks that need them; do not
disable existing services without checking their users. Check IPv6 separately.
Audit any existing Cloudflare tunnel as well as both system and gateway Funnel
routes: outbound tunnels can expose services despite a deny-incoming firewall.
The test website is currently intentionally public, not an authentication boundary.

Keep the OS, Docker, Tailscale and container images patched. Docker releases
before 28.0.0 have a documented same-L2-network caveat for localhost-published
ports; check vendor backports or upgrade rather than treating loopback binding
as sufficient isolation. See [Docker port publishing](https://docs.docker.com/engine/network/port-publishing/).

## Repository-enforced abuse limits

Each environment now has these Compose limits:

| Container | CPU ceiling | RAM ceiling | PID ceiling |
| --- | --- | --- | --- |
| Backend | 1.5 CPUs | 3 GiB | 128 |
| Frontend | 0.5 CPUs | 128 MiB | 64 |

Swap limits equal memory limits, preventing container swap growth. Two stacks
fit within the current 4-core / 16 GiB host with memory headroom for the OS,
gateway and other services. These are ceilings, not reservations. Terrain work
and page cache count toward the memory budget; measure representative large
requests after deployment and tune deliberately if necessary. OOM or PID-limit
failures are possible under load. The standalone gateway is unchanged.

Nginx limits aggregate `/api/` traffic to 10 requests/second per environment,
with an immediate burst allowance of 80; excess requests receive HTTP 429.
Static assets and `/healthz` are not throttled. The constant nonempty server name
is the bucket key, not client-supplied Host or forwarded IP headers. This is a
shared overload guard, not per-user fairness, authentication, an in-flight work
limit, or complete denial-of-service protection. The frontend currently surfaces
429 as an API error; it does not automatically retry throttled requests.

CI checks the resolved Compose limits and the live proxy's normal request burst,
429 response, resistance to spoofed headers, static access and recovery. Run the
traffic test only against an isolated test stack:

```sh
python3 -m unittest discover -s deploy -p 'test_*.py' -v
python3 deploy/check-api-limit.py http://127.0.0.1:18082
```

The unit suite requires Linux, Bash, `flock`, Python and Docker Compose (config
validation only; deployment commands are mocked). The traffic check needs a
running isolated stack with the new nginx configuration. Never load-test the
live test/production site as a substitute. `deploy/test_rulesets.py` needs only
Python's standard library and makes no GitHub calls. Merging these files does not
change GitHub/Tailscale protections or host firewall rules.

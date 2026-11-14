# Dedicated website hostname

This independent Compose project gives the website its own Tailscale device, `moon-flyers`, without renaming Beelink or changing its system Tailscale daemon, SSH, DNS settings, routes, or existing Funnel mappings.

Expected public URLs (confirm the actual assigned DNS name after login):

- Production: https://moon-flyers.tail644248.ts.net
- Test: https://moon-flyers.tail644248.ts.net:8443

GitHub still deploys over SSH to **beelink.tail644248.ts.net**. The gateway only proxies to the already-deployed loopback application ports `18080` and `18081`; it is not redeployed with each application release. Both public hostnames may work during migration because the existing system Funnel is deliberately left untouched.

## One-time setup

1. Add `tag:moon-flyers-funnel` to your tailnet's `tagOwners`, owned by administrators/owners. Add a `nodeAttrs` entry granting `funnel` to **only this tag**. See `../tailscale-policy.hujson`; merge the additions rather than replacing an existing policy.
2. Keep `tag:moon-flyers-server` exclusively on Beelink. Do not give the gateway that tag: CI's SSH grant targets it.
3. Copy this directory's `compose.yaml` and `serve.json` to `~/moon-flyers/gateway/` on Beelink. From that directory:

   ```sh
   # This file contains only public host/port routing, not credentials.
   # Container root has no DAC override capability, so a private host-owned
   # file copied with umask 077 would otherwise be unreadable inside it.
   chmod 0644 serve.json
   docker compose config --quiet
   docker compose up -d
   docker compose logs --tail 80 funnel
   ```

4. Open the Tailscale authorization URL shown in the logs and approve the new `moon-flyers` device. No auth key, OAuth secret, or host sudo configuration is required. If device approval is enabled, approve the device in the admin console too. Do not share authentication URLs or state files publicly.
5. Check the assigned DNS name and configuration:

   ```sh
   docker compose exec -T funnel tailscale status
   docker compose exec -T funnel tailscale funnel status
   docker compose ps
   python3 ../test/current/smoke-test.py https://moon-flyers.tail644248.ts.net:8443
   ```

   If the name is already taken, Tailscale may assign a suffix; use the actual DNS name instead of assuming the example. Production returns an upstream error until a production release has been deployed.
6. In GitHub repository **Settings → Secrets and variables → Actions → Variables**, set `PUBLIC_HOST` to the actual gateway FQDN, without a scheme or port. Leave `BEELINK_HOST` unchanged. The workflow needs the separate-public-host support from this branch before deployment summaries/public verification use the new hostname. The gateway itself can serve an existing app immediately.

## Persistence, isolation, and operation

- The named `state` volume holds the separate device identity and certificates. **It contains secrets**: do not commit, print, or copy it into release artifacts. Retain it across restarts and back it up securely if desired. Do not run `docker compose down -v` unless you intend to destroy this device identity and authenticate again.
- `TS_AUTH_ONCE=true` reuses that identity. The normal startup timeout is 30 minutes to allow initial human authorization. If the login URL expires, restart just this gateway and use its new authorization URL.
- `TS_USERSPACE=true`, no TUN device, no added capabilities, no SSH server, no subnet routes, and `TS_ACCEPT_DNS=false` keep it from reconfiguring the host's Tailscale networking. An automatically selected UDP port avoids conflicting with the system daemon.
- Host networking is intentionally used so the gateway can reach loopback-only app ports. It is **not** isolation from other host/LAN network services if the container is compromised. The container has no Docker socket or host Tailscale state/socket mounted.
- HTTPS/Funnel configuration is declarative in `serve.json`. Containerboot substitutes `${TS_CERT_DOMAIN}` with the authenticated device's certificate name. After a config/image change, ensure `serve.json` is still readable (`chmod 0644 serve.json`) and run `docker compose up -d --force-recreate funnel`; this also refreshes the bind mount after editors replace the file's inode. The named identity volume is retained. Verify both Funnel status and public HTTP afterward.
- Restarting or stopping this gateway affects the new website hostname only. Existing Beelink SSH and its system Funnel stay independent.

Useful commands, from `~/moon-flyers/gateway/`:

```sh
docker compose logs --tail 100 funnel
docker compose restart funnel
docker compose stop funnel
```

The deployment identity's CI tag has no SSH grant to this gateway. Keep node key expiry managed appropriately for an unattended server; tagged devices normally have expiry disabled. Review that setting in the Tailscale admin console.

Reference: [Tailscale Docker configuration](https://tailscale.com/kb/1282/docker).

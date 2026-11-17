#!/usr/bin/env bash
# Manual, root-only installation. Never run from the deployment workflow.
# Targets standard IPv4 Docker bridges; leaves the host-network Funnel alone.
set -euo pipefail

if [[ $(id -u) != 0 ]]; then
  echo 'Run this installer with sudo bash.' >&2
  exit 1
fi

helper=/usr/local/sbin/moon-flyers-egress
dropin=/etc/systemd/system/docker.service.d/50-moon-flyers-egress.conf
if [[ -e $helper || -e $dropin ]]; then
  echo 'STOP: a target file already exists; inspect/back it up before proceeding.' >&2
  exit 1
fi

install -d -m 755 /usr/local/sbin
cat > "$helper" <<'SCRIPT'
#!/bin/sh
set -eu

ipt() { /usr/sbin/iptables -w 10 "$@"; }

if ! ipt -nL DOCKER-USER >/dev/null 2>&1; then
    ipt -N DOCKER-USER
fi

# Update only this custom chain, never the complete managed firewall.
/usr/sbin/iptables-restore --wait 10 --noflush <<'RULES'
*filter
:MF-EGRESS-PERSIST - [0:0]
-F MF-EGRESS-PERSIST
-A MF-EGRESS-PERSIST -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
-A MF-EGRESS-PERSIST -m physdev --physdev-is-bridged -j RETURN
-A MF-EGRESS-PERSIST -d 100.100.100.100 -p udp --dport 53 -j RETURN
-A MF-EGRESS-PERSIST -d 100.100.100.100 -p tcp --dport 53 -j RETURN
-A MF-EGRESS-PERSIST -d 10.0.0.0/8 -j REJECT --reject-with icmp-admin-prohibited
-A MF-EGRESS-PERSIST -d 172.16.0.0/12 -j REJECT --reject-with icmp-admin-prohibited
-A MF-EGRESS-PERSIST -d 192.168.0.0/16 -j REJECT --reject-with icmp-admin-prohibited
-A MF-EGRESS-PERSIST -d 100.64.0.0/10 -j REJECT --reject-with icmp-admin-prohibited
-A MF-EGRESS-PERSIST -d 169.254.0.0/16 -j REJECT --reject-with icmp-admin-prohibited
-A MF-EGRESS-PERSIST -j RETURN
COMMIT
RULES

for interface in 'br+' docker0; do
    if ! ipt -C DOCKER-USER -i "$interface" -j MF-EGRESS-PERSIST 2>/dev/null; then
        ipt -I DOCKER-USER 1 -i "$interface" -j MF-EGRESS-PERSIST
    fi
done

if ! ipt -C FORWARD -j DOCKER-USER 2>/dev/null; then
    ipt -I FORWARD 1 -j DOCKER-USER
fi
SCRIPT
chmod 755 "$helper"

# A failed activation detaches only the new hooks and drops the new boot hook.
# Existing temporary MF-EGRESS rules are deliberately left untouched.
rollback() {
  /usr/sbin/iptables -w 10 -D DOCKER-USER -i br+ -j MF-EGRESS-PERSIST || true
  /usr/sbin/iptables -w 10 -D DOCKER-USER -i docker0 -j MF-EGRESS-PERSIST || true
  rm -f -- "$dropin"
  systemctl daemon-reload
}

# Schedule recovery before enabling the boot hook or applying the new policy.
systemd-run --unit=moon-flyers-persist-rollback --on-active=30m \
  /bin/sh -c '
    /usr/sbin/iptables -w 10 -D DOCKER-USER -i br+ -j MF-EGRESS-PERSIST || true
    /usr/sbin/iptables -w 10 -D DOCKER-USER -i docker0 -j MF-EGRESS-PERSIST || true
    rm -f /etc/systemd/system/docker.service.d/50-moon-flyers-egress.conf
    systemctl daemon-reload
  '
trap rollback ERR

install -d -m 755 /etc/systemd/system/docker.service.d
cat > "$dropin" <<'UNIT'
[Unit]
After=ufw.service

[Service]
ExecStartPre=/usr/local/sbin/moon-flyers-egress
ExecStartPost=/usr/local/sbin/moon-flyers-egress
UNIT

systemctl daemon-reload
"$helper"
/usr/sbin/iptables -w 10 -S DOCKER-USER
/usr/sbin/iptables -w 10 -nvL MF-EGRESS-PERSIST
printf '\nApplied without restarting Docker. Automatic rollback is scheduled in 30 minutes.\n'
printf 'Verify public URL, API, DNS, JPL HTTPS and LAN blocking before stopping the timer.\n'

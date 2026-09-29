#!/usr/bin/env bash
# Drive-Thru Intercom - one-time host hardening
# ================================================
# Run once per machine, as root: sudo bash scripts/harden.sh
#
# Does three things, in order:
#   1. Installs and configures fail2ban to lock out repeated failed SSH
#      login attempts (default: 5 tries / 10 min -> 1 hour ban).
#   2. Configures ufw (firewall) to default-deny incoming, but explicitly
#      allow: SSH from anywhere, and the dashboard port (8080) only from
#      this site's LAN subnet - the dashboard PIN is a shared-terminal
#      deterrent, not real auth, so it should never be reachable from the
#      open internet in the first place (see README's Security section).
#   3. Tightens filesystem permissions on this repo so config.yaml (PIN,
#      device MACs) and .session_secret aren't world/group-readable.
#
# Does NOT touch SSH password-vs-key auth - this box is left on password
# login intentionally (a deliberate choice made with the operator, not an
# oversight). Re-run this script safely any time; every step is
# idempotent.
#
# LAN_SUBNET below is this site's actual LAN (192.168.50.0/24, confirmed
# via `ip -4 addr show` on this box) - EDIT THIS if you're running this
# script on a different site/network before running it.

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this as root: sudo bash $0" >&2
    exit 1
fi

LAN_SUBNET="192.168.50.0/24"
DASHBOARD_PORT="8080"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_USER="$(stat -c '%U' "$REPO_DIR")"

echo "==> Repo: $REPO_DIR (owner: $REPO_USER)"
echo "==> LAN subnet for dashboard access: $LAN_SUBNET"
echo

# --- 1. fail2ban -------------------------------------------------------
echo "==> Installing fail2ban..."
apt-get update -qq
apt-get install -y -qq fail2ban

install -d -m 755 /etc/fail2ban/jail.d
cat > /etc/fail2ban/jail.d/drivethru-sshd.conf <<'EOF'
# Drive-Thru Intercom - SSH brute-force protection.
[sshd]
enabled = true
port = ssh
filter = sshd
backend = systemd
maxretry = 5
findtime = 10m
bantime = 1h
EOF

systemctl enable fail2ban --now
systemctl restart fail2ban
echo "    fail2ban active: $(fail2ban-client status sshd 2>/dev/null | grep 'Status' || echo 'jail starting...')"
echo

# --- 2. ufw firewall -----------------------------------------------------
echo "==> Configuring ufw..."
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh comment 'SSH - fail2ban covers brute force'
ufw allow from "$LAN_SUBNET" to any port "$DASHBOARD_PORT" proto tcp comment 'Dashboard - LAN only, never public internet'
ufw --force enable
ufw status verbose
echo

# --- 3. filesystem permissions -----------------------------------------
echo "==> Tightening file permissions on $REPO_DIR..."
chmod 750 "$REPO_DIR"
[ -f "$REPO_DIR/config.yaml" ] && chmod 600 "$REPO_DIR/config.yaml"
[ -f "$REPO_DIR/.session_secret" ] && chmod 600 "$REPO_DIR/.session_secret"
[ -f "$REPO_DIR/drivethru.db" ] && chmod 600 "$REPO_DIR/drivethru.db"
echo "    done."
echo

echo "==> Hardening complete."
echo "    - SSH: password login still works, fail2ban bans after 5 failed attempts/10min"
echo "    - Firewall: only SSH (any source) and port $DASHBOARD_PORT (LAN only) are reachable"
echo "    - config.yaml/.session_secret/drivethru.db are now owner-only (600)"
echo
echo "Check ban status any time with: sudo fail2ban-client status sshd"
echo "Check firewall rules any time with: sudo ufw status verbose"

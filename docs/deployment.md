# Deployment

## GCP VM Details

- **Instance**: `myfeeds`
- **Zone**: `us-central1-a`
- **External IP**: `34.61.25.130`
- **App URL**: `http://34.61.25.130`

## Deploy Changes

**Full deploy** (Python/dependency/config changes):
```bash
gcloud compute ssh myfeeds --zone=us-central1-a --project=glossy-reserve-153120 --command="sudo bash -c 'cd /opt/MyFeeds && git pull && docker-compose up -d --build'"
```

**Static-only deploy** (JS/CSS changes — no rebuild needed):
```bash
gcloud compute ssh myfeeds --zone=us-central1-a --project=glossy-reserve-153120 --command="sudo bash -c 'cd /opt/MyFeeds && git pull'"
```

Static files are mounted as a volume, so `git pull` makes them live instantly.

Note: Use `docker-compose` (hyphenated) not `docker compose` on this VM.

## Prerequisites

- Changes must be committed and pushed to `master` before deploying
- `gcloud` CLI must be authenticated (`gcloud auth login`)

## Troubleshooting

If docker-compose fails with `ContainerConfig` error (common when volumes or config changed), run with explicit down first:
```bash
docker-compose down && docker-compose up -d --build
```

## VM operations: maintenance, monitoring & access

This VM produced two recurring alerts with **different root causes** — don't conflate them:

- **High CPU = Ubuntu `unattended-upgrades`.** The daily apt job (heaviest on kernel-upgrade weeks: image download + initramfs regen) briefly pushes the 10-min CPU mean over threshold. Pinned to a known Monday window (below).
- **High egress = external HTTP traffic to the app, NOT apt.** A packet capture (May 2026) showed the egress was the public, then-unauthenticated app serving article pages to external clients/scrapers over port 80. Apt downloads are *inbound*, not egress, and there is no logging agent shipping logs out — so apt was never the egress source. Adding login auth (below) removes anonymous access and should largely eliminate these egress alerts.

They looked correlated only by coincidence: apt runs daily, scraping happens at random times, so they occasionally overlapped. An earlier version of this doc wrongly attributed egress to maintenance — it doesn't.

### Pinned maintenance window

`apt-daily-upgrade.timer` is pinned to **Mon 14:00 UTC** (07:00 PDT / 06:00 PST) via `/etc/systemd/system/apt-daily-upgrade.timer.d/override.conf`:

```
[Timer]
OnCalendar=
OnCalendar=Mon 14:00 UTC
RandomizedDelaySec=0
Persistent=true
```

Smaller dpkg transactions and quieter logs via `/etc/apt/apt.conf.d/55unattended-upgrades-myfeeds.conf`:

```
Unattended-Upgrade::AutoFixInterruptedDpkg "true";
Unattended-Upgrade::MinimalSteps "true";
Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";
Unattended-Upgrade::Remove-New-Unused-Dependencies "true";
Unattended-Upgrade::Verbose "false";
```

The apt service itself is CPU-capped to 30% of one core via `/etc/systemd/system/apt-daily-upgrade.service.d/cpu-limit.conf`:

```
[Service]
CPUQuota=30%
```

This throttles the whole service tree (apt, dpkg, `initramfs-update`, all children). `MinimalSteps` spreads work *between* transactions, but operations like initramfs regeneration are a single atomic subprocess — the cap is what flattens those. Tradeoff: apt takes longer (~3× wall clock), which is intentional and irrelevant at Mon 07:00 PDT when the VM is otherwise idle. **If this cap is ever removed, expect the CPU alert to fire harder and the alert calibration may need re-tuning.**

`apt-daily.timer` (package-list refresh) is left at its default — it doesn't produce visible spikes.

### Reapplying after VM rebuild

All three files live on the VM, not in this repo. If the VM is recreated, run:

```bash
gcloud compute ssh myfeeds --zone=us-central1-a --project=glossy-reserve-153120 \
  --command="sudo mkdir -p /etc/systemd/system/apt-daily-upgrade.timer.d /etc/systemd/system/apt-daily-upgrade.service.d && \
  printf '[Timer]\nOnCalendar=\nOnCalendar=Mon 14:00 UTC\nRandomizedDelaySec=0\nPersistent=true\n' | \
    sudo tee /etc/systemd/system/apt-daily-upgrade.timer.d/override.conf && \
  printf '[Service]\nCPUQuota=30%%\n' | \
    sudo tee /etc/systemd/system/apt-daily-upgrade.service.d/cpu-limit.conf && \
  printf 'Unattended-Upgrade::AutoFixInterruptedDpkg \"true\";\nUnattended-Upgrade::MinimalSteps \"true\";\nUnattended-Upgrade::Remove-Unused-Kernel-Packages \"true\";\nUnattended-Upgrade::Remove-New-Unused-Dependencies \"true\";\nUnattended-Upgrade::Verbose \"false\";\n' | \
    sudo tee /etc/apt/apt.conf.d/55unattended-upgrades-myfeeds.conf && \
  sudo systemctl daemon-reload && sudo systemctl restart apt-daily-upgrade.timer"
```

Verify with:
```bash
systemctl list-timers apt-daily-upgrade.timer
systemctl show apt-daily-upgrade.service -p CPUQuotaPerSecUSec
sudo apt-config dump | grep -E 'Unattended-Upgrade::(MinimalSteps|Remove-Unused-Kernel-Packages|Verbose)'
```

### Authentication & access control

The app requires a password login (cookie-based session). All routes are gated except `/health` (Docker healthcheck) and `/static/` (login page assets).

- Auth is active only when `APP_PASSWORD` is set; unset = open (local dev / tests).
- Secrets live in `/opt/MyFeeds/.env` (chmod 600, gitignored — never in the repo):
  - `APP_PASSWORD` — the login password.
  - `SECRET_KEY` — 256-bit random hex; signs the session cookie. A weak/default key would let the cookie be forged, so this must be strong and stable.
- Sessions persist 1 year (`PERMANENT_SESSION_LIFETIME`), so each device logs in once and stays signed in.
- Access logging is on (`--access-logfile -` in `entrypoint.sh`): client IP, path, status, bytes, user-agent appear in `docker logs myfeeds_myfeeds_1`. Logs stay local (no logging agent); rotation is capped in `docker-compose.yml` (10 MB × 3 files per container).

Rotate the password: edit `APP_PASSWORD` in `/opt/MyFeeds/.env`, then `docker-compose up -d` to recreate the web container. Changing `SECRET_KEY` invalidates all sessions (forces re-login everywhere). After a VM rebuild, recreate `/opt/MyFeeds/.env` — it is not in the repo.

**Firewall / network:** port 80 is public (app reachable anywhere; auth gates it). SSH (22) is public but **key-only** (`PasswordAuthentication no`), so brute-force noise cannot succeed. The `default-allow-rdp` rule was deleted (Linux VM, unused). CPU/egress metrics are hypervisor-level (no in-VM agent).

### Alert policies (Cloud Monitoring)

Four policies cover CPU and egress in a two-tier layout per metric.

**Sensitive tier:**

- `MyFeeds VM - High CPU Alert (10-min mean >75%)` — 10-min rolling mean of CPU > 75%, no retest. **Expected to fire briefly each Monday** during the Mon 14:00 UTC `apt-daily-upgrade` run; its doc text says so. Investigate only if it fires *outside* the Mon 13:55–14:30 UTC window.
- `MyFeeds VM - High Network Egress Alert` — 1-hour rolling rate of egress > 2 KiB/s, no retest. **Not tied to maintenance.** Fires on sustained outbound HTTP — historically external scraping of the then-open app. With login auth now in place this should rarely fire; if it does, check `docker logs` access lines for the client IPs and what they pulled. The 1-hour rolling rate lags ~1 hour behind the actual traffic.

**Always-on safety tier — should never fire during maintenance:**

- `MyFeeds VM - Sustained High CPU` — same metric/aggregation as the sensitive CPU policy, threshold 90%, Warning severity.
- `MyFeeds VM - Sustained High Egress` — same metric/aggregation as the sensitive egress policy, threshold 10 KiB/s, Warning severity.

Both always-on policies use the same aggregation as their sensitive counterpart (10-min mean for CPU, 1-hour rate for egress) so they are genuinely "two thresholds on the same signal" rather than two adjacent signals. If either fires, treat as a real anomaly — likely a runaway process, scrape, or compromise.

**Note on snoozes:** A recurring weekly snooze would suppress the expected Monday emails entirely, but the Cloud Console UI in this project only supports one-shot snoozes — there is no native recurring/weekly option. Rather than build IaC for what amounts to one expected email per metric per week, the design lives with the weekly fires and uses the doc text to explain them inline. If recurring snoozes ship in the Console, revisit.

All four policies are managed in Cloud Console (Monitoring → Alerting → Policies), not in this repo.

### Investigating a future alert

**A Monday-morning CPU alert (~14:00–14:18 UTC)** is expected apt maintenance — confirm via `apt history.log` and move on.

**Any egress alert, an always-on alert, or a CPU alert outside the Monday window** warrants a look. The access log now shows exactly who is hitting the app:

```bash
gcloud compute ssh myfeeds --zone=us-central1-a --project=glossy-reserve-153120 --command="\
  WEB=\$(sudo docker ps --filter name=myfeeds_myfeeds -q | head -1); \
  echo '--- top client IPs (last 1h) ---'; sudo docker logs --since 1h \$WEB 2>&1 | grep -oE '^[0-9.]+' | sort | uniq -c | sort -rn | head; \
  echo '--- recent requests ---'; sudo docker logs --since 1h \$WEB 2>&1 | grep -E '\"(GET|POST)' | tail -30; \
  echo '--- apt history ---'; sudo zgrep -h '' /var/log/apt/history.log* | tail -20"
```

Pre-auth, egress was anonymous external scraping. Post-auth, sustained egress more likely means heavy legitimate use or a stuck/looping client — the access log's IPs and user-agents will tell you which.

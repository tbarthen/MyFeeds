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

`apt-daily.service` (the package-list refresh unit) is capped the same way via `/etc/systemd/system/apt-daily.service.d/cpu-limit.conf` — it was the one remaining uncapped apt unit.

### CPU spike forensics (detection harness)

On 2026-07-06 the always-on 90% CPU tier fired at the tail of the Monday apt window (10-min mean → 99.8%), but **no retrospective log could attribute it**: apt was capped and used only 3 min CPU, no service restarted, no worker wedged. The box has no per-process CPU history (no atop/sysstat), so attribution was impossible after the fact.

`/usr/local/bin/cpu-forensics.sh` + `cpu-forensics.timer` fix that. Every minute the script computes the **60-second mean** CPU% and steal% from the `/proc/stat` delta since the previous tick (prev counters cached in `/run/cpu-forensics.prev`, tmpfs) and **always** appends one lightweight line to `/var/log/cpu-forensics.log`:

```
TICK 2026-07-13T14:05:00Z cpu=8.3% st=1.2% load=0.30
```

`cpu` is busy incl. steal (matches the alert signal); `st` is the steal component broken out. When the minute-mean is ≥70% it *additionally* appends a `DETAIL` block — a `top` snapshot with the `%Cpu(s)` line (incl. `st`) plus the hottest PID's **cgroup and cmdline**:

```
===== 2026-07-13T14:05:00Z DETAIL cpu=99.8% st=0.1% =====
%Cpu(s): 99.0 us, 0.5 sy, ... 0.5 st
  PID USER ... %CPU COMMAND
  ...
-- hottest PID 12345 cgroup: 0::/system.slice/...
-- cmdline: ...
```

The log is size-capped at 1 MB (self-truncating to the tail 512 KB). At ~55 B/tick that is roughly a week and a half of unconditional history; local only, no egress, $0.

**Reading it** — the always-on `TICK` trend is what resolves the 2026-07-06 ambiguity. During an alert window, `grep '^TICK'` shows exactly what in-guest CPU and steal were, minute by minute:
- `TICK` cpu high (some `DETAIL` block names a hot process/cgroup) → real in-guest work; attribute via the cgroup (apt vs a container vs host).
- `TICK` cpu low but `st` high → **hypervisor CPU steal** on this shared-core e2-micro (noisy neighbor); not our runaway — adjust the alert, don't chase.
- Alert says ~99% but `TICK` cpu **and** `st` are both low → the GCE metric doesn't reflect in-guest work at all → **hypervisor/metric artifact**, not an in-guest event. (Previously this case left an *empty* log, indistinguishable from "sampler missed it"; the per-tick line makes it a positive finding.)

```bash
gcloud compute ssh myfeeds --zone=us-central1-a --project=glossy-reserve-153120 \
  --command="sudo grep '^TICK' /var/log/cpu-forensics.log | tail -30; echo ---; sudo grep -A20 DETAIL /var/log/cpu-forensics.log | tail -60"
```

### Reapplying after VM rebuild

These VM-side files are not in this repo. If the VM is recreated, reapply the apt timer/caps:

```bash
gcloud compute ssh myfeeds --zone=us-central1-a --project=glossy-reserve-153120 \
  --command="sudo mkdir -p /etc/systemd/system/apt-daily-upgrade.timer.d /etc/systemd/system/apt-daily-upgrade.service.d /etc/systemd/system/apt-daily.service.d && \
  printf '[Timer]\nOnCalendar=\nOnCalendar=Mon 14:00 UTC\nRandomizedDelaySec=0\nPersistent=true\n' | \
    sudo tee /etc/systemd/system/apt-daily-upgrade.timer.d/override.conf && \
  printf '[Service]\nCPUQuota=30%%\n' | \
    sudo tee /etc/systemd/system/apt-daily-upgrade.service.d/cpu-limit.conf && \
  printf '[Service]\nCPUQuota=30%%\n' | \
    sudo tee /etc/systemd/system/apt-daily.service.d/cpu-limit.conf && \
  printf 'Unattended-Upgrade::AutoFixInterruptedDpkg \"true\";\nUnattended-Upgrade::MinimalSteps \"true\";\nUnattended-Upgrade::Remove-Unused-Kernel-Packages \"true\";\nUnattended-Upgrade::Remove-New-Unused-Dependencies \"true\";\nUnattended-Upgrade::Verbose \"false\";\n' | \
    sudo tee /etc/apt/apt.conf.d/55unattended-upgrades-myfeeds.conf && \
  sudo systemctl daemon-reload && sudo systemctl restart apt-daily-upgrade.timer"
```

The CPU-forensics harness (`/usr/local/bin/cpu-forensics.sh`, `cpu-forensics.service`, `cpu-forensics.timer`) also lives only on the VM; its current source is the per-tick script deployed 2026-07-07 (60s-delta `TICK` line every minute + `DETAIL` on ≥70%, described above) — recreate it and `systemctl enable --now cpu-forensics.timer` if the VM is rebuilt.

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

### Access-log shipping (Cloud Logging)

The web container's access lines are local-only in `docker logs` (json-file, 10 MB × 3 ≈ 2 weeks) — which meant egress incidents older than that were unattributable (e.g. the Jul 5 window was already gone by Jul 20). `/usr/local/bin/access-log-ship.py` + `access-log-ship.timer` fix that: every minute the script pulls new `GET/POST/HEAD` lines via `docker logs --since`, and POSTs them to Cloud Logging (`projects/glossy-reserve-153120/logs/myfeeds-access`) using the VM service account's metadata token — **no Ops Agent** (the 1 GB box has no memory headroom for one; 0 swap) and **no cost** (~14 MB/month vs the 50 GB/month free tier). State (last-shipped epoch) is in `/run` (tmpfs). It ships *only* access lines, not the chatty scheduler/healthcheck noise beyond `/health`.

Query without SSH:
```bash
gcloud logging read 'logName="projects/glossy-reserve-153120/logs/myfeeds-access"' \
  --project=glossy-reserve-153120 --limit=50 --freshness=2h --format='value(timestamp,textPayload)'
```

Like the other VM-side helpers this is not in the repo; recreate `/usr/local/bin/access-log-ship.py` + `access-log-ship.service`/`.timer` and `systemctl enable --now access-log-ship.timer` after a VM rebuild. `docker logs` local retention is unchanged (json-file driver kept), so the SSH fallback still works.

### Alert policies (Cloud Monitoring)

Four policies cover CPU and egress in a two-tier layout per metric.

**Sensitive tier:**

- `MyFeeds VM - High CPU Alert (10-min mean >75%)` — 10-min rolling mean of CPU > 75%, no retest. **Fires on Monday apt mornings but does NOT reflect real in-guest load.** The cpu-forensics TICK log (since 2026-07-07) shows in-guest CPU never exceeds ~16% in these windows — on 2026-07-20 it was ~1% at the moment the alert opened, steal 0%, and there have been **zero** DETAIL (≥70%) blocks in 13 days. The apt CPU cap (30% of one core) is holding; the metric reads high because the shared-core e2-micro `cpu/utilization` normalizes against the fractional baseline vCPU. **This is a hypervisor metric artifact, not app load** — there is no app job at 14:00 UTC (the scheduler is interval-based; `cleanup` runs at :23, `refresh` drifts). Verify any CPU alert against the TICK log before treating it as real.
- `MyFeeds VM - High Network Egress Alert` — 1-hour rolling rate of egress > 2 KiB/s, no retest. **Not tied to maintenance.** Attribution as of 2026-07-20: egress is dominated by *legitimate authenticated reads* — `GET /` article pages of 20–58 KB pulled by the owner's own IPs (Verizon/Visible mobile + home). Scanner noise is high-count but low-byte (207-byte 404s, 1.7 KB login pages), already neutralized by the login wall + tiny-404 change. Because the bytes are real content (not probe noise), the **threshold stays at 2 KiB/s** — raising it would hide genuine anomalies just to mask the owner's own reading. The 1-hour rolling rate lags ~1 hour behind traffic; a reading session briefly crests 2 KiB/s and auto-closes.

**Always-on safety tier — should never fire during maintenance:**

- `MyFeeds VM - Sustained High CPU` — same metric/aggregation as the sensitive CPU policy, threshold 90%, Warning severity. **Caveat:** because it reads the same shared-core metric, this tier has *also* fired on Monday apt windows (e.g. 2026-07-20) despite in-guest CPU ≤16% — so a Monday firing is not automatically a real runaway. Confirm against the TICK log; it is meaningful *off*-Monday or whenever the TICK log actually shows cpu ≥ 70% with a DETAIL block.
- `MyFeeds VM - Sustained High Egress` — same metric/aggregation as the sensitive egress policy, threshold 10 KiB/s, Warning severity.

The egress pair are genuinely "two thresholds on the same signal." The CPU pair share a *metric-artifact-prone* signal on this shared-core VM — treat CPU firings as suspect until the TICK log confirms real in-guest load. A future improvement would be a CPU alert keyed to an in-guest signal (e.g. shipping the TICK values as a custom metric) rather than the hypervisor `cpu/utilization`.

**Note on snoozes:** A recurring weekly snooze would suppress the expected Monday emails entirely, but the Cloud Console UI in this project only supports one-shot snoozes — there is no native recurring/weekly option. Rather than build IaC for what amounts to one expected email per metric per week, the design lives with the weekly fires and uses the doc text to explain them inline. If recurring snoozes ship in the Console, revisit.

All four policies are managed in Cloud Console (Monitoring → Alerting → Policies), not in this repo.

### Investigating a future alert

**Any CPU alert** — verify against the in-guest TICK log first; on this shared-core VM the CPU metric is artifact-prone (see Alert policies above):

```bash
gcloud compute ssh myfeeds --zone=us-central1-a --project=glossy-reserve-153120 \
  --command="sudo grep '^TICK' /var/log/cpu-forensics.log | tail -30"
```

If the TICK `cpu=` values stay under ~20% during the alert window (and there is no `DETAIL` block), it is the metric artifact — no action. A real runaway shows cpu ≥ 70% and a `DETAIL` block naming the process/cgroup.

**Any egress alert** — the web access log is shipped to Cloud Logging (see *Access-log shipping* below), so attribution no longer needs SSH:

```bash
gcloud logging read 'logName="projects/glossy-reserve-153120/logs/myfeeds-access"' \
  --project=glossy-reserve-153120 --limit=200 --freshness=2h \
  --format='value(textPayload)' | grep -vE '^(127\.0\.0\.1|172\.)' \
  | awk '{print $1}' | sort | uniq -c | sort -rn | head
```

The sent-bytes metric lags ~1 hour, so widen `--freshness` to cover the hour *before* the incident opened. Big `GET /` 200s (20–58 KB) to the owner's IPs = legitimate reads (benign); many tiny 404s/302s = neutralized scanner noise. Real content pulled by an *unfamiliar* IP would be the exception worth chasing. Local `docker logs myfeeds_myfeeds_1` remains available over SSH as a fallback (2-week retention).

**Benign one-off: an admin DB/OPML pull.** A single `gcloud compute scp` of the database off the VM (`myfeeds.db` ≈ 6 MB, or a DB + access-log grab ≈ 7–8 MB with SSH overhead) averages to ~2.3 KB/s over the 1-hour rate window — just over the 2 KiB/s sensitive threshold — so it trips `High Network Egress Alert` for exactly one hour and then clears on its own. This is hypervisor-level (SSH/scp) egress, so it will **not** appear in the `docker logs` access lines above — don't waste time hunting for a client IP. Confirmed 2026-07-05 (incident details from the Console): the accidental-deletion recovery scp of the 6 MB DB + 1 MB access log opened an incident at 11:42 UTC that ran 59 min and peaked at 2.24 KiB/s — *just* over the 2 KiB/s line — then auto-closed once the burst aged out of the rolling hour; CPU and the always-on 10 KiB/s tier stayed quiet. **Signature to recognize:** a ~1-hour incident that barely crosses the threshold and then closes on its own is a single one-time transfer aging through the rolling window — not sustained scraping, which runs longer and/or higher. If an egress alert has that shape and lines up with a known admin download, it's this — no action needed.

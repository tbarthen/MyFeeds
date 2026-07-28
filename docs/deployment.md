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

### What actually costs money (verified 2026-07-27)

Billing was investigated end-to-end because the alerts were assumed to be cost warnings. They are not. Actual spend is **$0.34/month**, and the SKU report shows why:

| SKU | Gross | After free-tier credits |
|---|---|---|
| E2 Instance Core + E2 Instance Ram | $5.34 | **$0.34** ← the entire bill |
| Cloud Run functions CPU (market-close) | $3.56 | $0.00 |
| Network Intelligence Center | $1.21 | $0.00 |
| **External IP Charge on a Standard VM** (638 h) | — | **$0.00** |
| Storage PD Capacity, all data transfer, Secret Manager | — | $0.00 |

**The bill is the VM existing, not the VM working.** A fixed-size instance bills by the hour — E2 Core/Ram charge identically at 1% or 100% CPU. Consequences:

- **CPU utilization can never produce a charge on this VM.** E2 shared-core bursting is included in the hourly price (unlike AWS T-series credits). A CPU alert is a *health/compromise* signal, never a billing signal.
- **Only genuinely metered things:** internet egress beyond 1 GB/mo, disk beyond 30 GB, function calls beyond 2M/mo, Cloud Logging beyond 50 GB/mo.
- **Current headroom:** egress **0.46 GB/mo (46%)** — measured from `/proc/net/dev` TX over 174 days uptime; disk 10 of 30 GB; functions ~22 of 2M calls; logging ~14 MB of 50 GB.

**Cost protection is the budget, not the alerts.** `MyFeeds RSS Reader Budget` ($1, thresholds 50/90/100%) publishes to the `budget-alerts` Pub/Sub topic, which triggers the `stop-vm-on-budget` function to halt the VM. That backstop catches *any* cost source, including ones no per-metric alert watches. Note it **stops the VM** at 100% — the reader goes offline until manually restarted, so keep the budget comfortably above the ~$0.34 baseline.

### Alert policies (Cloud Monitoring)

Four policies cover CPU and egress in a two-tier layout per metric. Given the cost model above, **their purpose is security/health detection, not cost control** — the budget owns cost.

**Sensitive tier:**

- `MyFeeds VM - High CPU Alert` — **re-keyed 2026-07-27** to `compute.googleapis.com/instance/cpu/usage_time` (ALIGN_RATE, 600 s window, threshold **> 1.0 CPU-second/second** of the 2.0 available on this 2-vCPU instance). It was previously `cpu/utilization > 75%`, which **fired on Monday apt mornings without reflecting real in-guest load.** The cpu-forensics TICK log (since 2026-07-07) shows in-guest CPU never exceeds ~16% in these windows — on 2026-07-20 it was ~1% at the moment the alert opened, steal 0%, and there have been **zero** DETAIL (≥70%) blocks in 13 days. The apt CPU cap (30% of one core) is holding; the metric reads high because the shared-core e2-micro `cpu/utilization` normalizes against the fractional baseline vCPU. **This is a hypervisor metric artifact, not app load** — confirmed on two consecutive Mondays (2026-07-20 and 2026-07-27: in-guest ≤17%, 0 DETAIL, while the GCE metric read up to **105.98%** — and >100% is impossible for real in-guest CPU, which is itself proof of the baseline-vCPU normalization). The `telemetryJobID` / `Scheduler - wake` lines the Console shows at 14:00:54 UTC are **Google's GCE Guest Agent** (`logName=projects/…/logs/GCEGuestAgent`), a daily system telemetry ping — **not** the MyFeeds app (whose scheduler is interval-based and isn't shipped to Cloud Logging at all; only `myfeeds-access` is). Nothing to reschedule. **Why `usage_time` fixes it:** it counts absolute CPU-seconds consumed, so it is immune to the baseline-vCPU normalization that produced the >100% readings. Measured apt maintenance = ~0.32 CPU-s/s (16% of 2 cores), so a 1.0 threshold sits ~3× above the artifact while still catching a genuine runaway (a miner pegging both cores reads ~2.0). Verify any CPU alert against the TICK log before treating it as real.
- `MyFeeds VM - High Network Egress Alert` — 1-hour rolling rate of egress > 2 KiB/s, no retest. **Not tied to maintenance.** Attribution as of 2026-07-20: egress is dominated by *legitimate authenticated reads* — `GET /` article pages of 20–58 KB pulled by the owner's own IPs (Verizon/Visible mobile + home). Scanner noise is high-count but low-byte (207-byte 404s, 1.7 KB login pages), already neutralized by the login wall + tiny-404 change. Because the bytes are real content (not probe noise), the **threshold stays at 2 KiB/s** — raising it would hide genuine anomalies just to mask the owner's own reading. **Window widened 2026-07-27 from a 1-hour to a 24-hour rolling rate; the 2 KiB/s threshold is retained.** The threshold was always cost-calibrated and remains correct: 2,000 B/s sustained = 165 MB/day = **5.2 GB/month vs the 1 GB free tier** ≈ $0.50/mo overage. The *window* was the defect — a 1-hour rate let a 20-minute reading session cross the line and then decay, answering "was one hour busy?" instead of "am I on pace for the month?". Over 24 hours the bursts average out: measured sustained egress is **178 B/s, ~9% of the threshold**. It now fires only when genuinely on pace to exceed the free tier — exactly its original intent.

**Always-on safety tier — should never fire during maintenance:**

- `MyFeeds VM - Sustained High CPU` — **re-keyed 2026-07-27** to `cpu/usage_time` (ALIGN_RATE, 600 s) at **> 1.6 CPU-seconds/second** (80% of the 2.0 available), Warning severity. Previously `cpu/utilization > 90%`, which also fired on Monday apt windows despite in-guest CPU ≤17%. At 1.6 CPU-s/s only a genuine sustained runaway can trip it.
- `MyFeeds VM - Sustained High Egress` — 10 KiB/s, 1-hour rolling rate, Warning severity. **Unchanged** — it has never false-fired, and at 10 KiB/s a firing is a real anomaly (exfiltration, scrape, stuck client), not normal reading.

**Why these are health signals, not cost signals.** Cost is owned by the budget + `stop-vm-on-budget` kill switch (see *What actually costs money*). These four exist to detect a compromised or malfunctioning VM — a miner pegging the CPU, or data being pulled out. That distinction is why the CPU pair were re-keyed rather than deleted: they were never able to predict a charge, but they *are* the only automated signal for a compromised host.

**Design rule going forward:** before adding or tuning an alert here, state which of the two jobs it does — *predict a charge* (then it must key off a genuinely metered quantity: cumulative egress GB, disk GB, invocation counts — never CPU%) or *detect compromise/malfunction* (then calibrate it against measured normal behaviour from the TICK log and access log, not intuition about what a "simple RSS reader" should use).

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

# Deployment

## GCP VM Details

- **Instance**: `myfeeds`
- **Zone**: `us-central1-a`
- **External IP**: `34.61.25.130`
- **App URL**: `http://34.61.25.130`

## Deploy Changes

**Full deploy** (Python/dependency/config changes):
```bash
gcloud compute ssh myfeeds --zone=us-central1-a --project=glossy-reserve-153120 --command="sudo bash -c 'cd /opt/MyFeeds && git pull && DOCKER_BUILDKIT=1 docker-compose up -d --build'"
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

If docker-compose fails with `ContainerConfig` error, run with explicit down first:
```bash
docker-compose down && DOCKER_BUILDKIT=1 docker-compose up -d --build
```

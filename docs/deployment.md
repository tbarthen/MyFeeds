# Deployment

## GCP VM Details

- **Instance**: `myfeeds`
- **Zone**: `us-central1-a`
- **External IP**: `34.61.25.130`
- **App URL**: `http://34.61.25.130`

## Deploy Changes

```bash
gcloud compute ssh myfeeds --zone=us-central1-a --project=glossy-reserve-153120 --command="sudo bash -c 'cd /opt/MyFeeds && git pull && docker-compose down && docker-compose up -d --build'"
```

Note: Use `docker-compose` (hyphenated) not `docker compose` on this VM.

## Prerequisites

- Changes must be committed and pushed to `master` before deploying
- `gcloud` CLI must be authenticated (`gcloud auth login`)

## Troubleshooting

If docker-compose fails with `ContainerConfig` error, run with `down` first:
```bash
docker-compose down && docker-compose up -d --build
```

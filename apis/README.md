# Glance Dashboard APIs

Small Flask services that turn awkward upstream APIs into flat JSON that Glance `custom-api` widgets can template easily.

## Live APIs

| API | Host | Port | Endpoints | Used by (page) |
|-----|------|------|-----------|----------------|
| [service-version-api](service-version-api/) | docker-vm-core-utilities01 (192.168.40.13) | 5070 | `/api/services`, `/api/services/<category>`, `/api/summary`, `/api/update/<name>?key=`, `/api/update-status/<id>`, `/refresh`, `/health` | Services (health, versions, one-click updates) |
| [nas-backup-status-api](nas-backup-status-api/) | 192.168.40.13 | 9102 | `/status`, `/backups`, `/job-status`, `/refresh`, `/health` | Backup |
| [life-progress](life-progress/) | 192.168.40.13 | 5051 | `/progress`, `/health` | Home |
| [steam-stats](steam-stats/) | 192.168.40.13 | 5055 | `/stats`, `/health` | Home |
| [pihole-stats-api](pihole-stats-api/) | docker-lxc-glance (192.168.40.12) | 5055 | `/api/pihole/stats`, `/health` | Network (called from the Glance container via `172.17.0.1:5055`) |
| [proxmox-nodes-api](proxmox-nodes-api/) | docker-lxc-glance (192.168.40.12) | 5061 | `/api/nodes`, `/health` | Running, but no longer referenced by `glance.yml` |

Glance also reads Prometheus (`192.168.40.13:9090`), the Proxmox and PBS APIs, the Radarr/Sonarr/Prowlarr APIs, Speedtest Tracker (`192.168.40.13:3000`) and embeds Grafana dashboards. Those are standard services and are not in this folder.

## Configuration

| API | Variables |
|-----|-----------|
| service-version-api | `UPDATE_API_KEY` (shared secret for update buttons; must match `SERVICE_VERSION_API_KEY` in Glance's `.env`). Mounts `~/.ssh` read-only to query and update containers on other hosts over SSH. |
| nas-backup-status-api | None. Mounts `~/.ssh` read-only and SSHes to PBS (`192.168.20.50`). |
| life-progress | `BIRTH_DATE` (ISO date), `TARGET_AGE` |
| steam-stats | `STEAM_API_KEY`, `STEAM_ID` (Steam64). Get a key at https://steamcommunity.com/dev/apikey |
| pihole-stats-api | `PIHOLE_PASSWORD` (required), `PIHOLE_URL` (default `http://192.168.90.53`). Pi-hole v6 API. |
| proxmox-nodes-api | None. Reads node status from Prometheus. |

Put variables in a `.env` next to each `docker-compose.yml` (never commit it).

## Deploy

```bash
# on the target host
sudo mkdir -p /opt/<api> && sudo chown $USER /opt/<api>
cp -r apis/<api>/* /opt/<api>/
cd /opt/<api> && nano .env   # if the API needs variables
docker compose up -d --build
curl -s localhost:<port>/health
```

`pihole-stats-api` and `proxmox-nodes-api` don't need a build; they bind-mount the script into `python:3.11-slim`.

## Retired

[`_retired/`](_retired/) keeps APIs that are no longer wired into the dashboard, kept for reference:

| API | Why retired |
|-----|-------------|
| health-tracker-api (5062) | Health page removed 2026-08-29 |
| nba-stats-api (5060) | Sports page removed 2026-08-29 |
| media-stats-api (5054) | Media page now queries Radarr/Sonarr directly |
| docker-stats-exporter (9417) | Not running; container metrics come from cAdvisor + Prometheus |
| power-control-api (5057) | Power panel removed from Home; the container still runs on .13 |

## Testing

```bash
curl -s http://192.168.40.13:5070/api/summary | jq .
curl -s http://192.168.40.13:9102/status | jq .
curl -s http://192.168.40.13:5051/progress | jq .
curl -s http://192.168.40.13:5055/stats | jq .
curl -s http://192.168.40.12:5055/api/pihole/stats | jq .
```

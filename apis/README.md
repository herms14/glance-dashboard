# Glance Dashboard APIs

Custom Python APIs that provide data to the Glance dashboard widgets.

## APIs

| API | Port | Endpoint | Description |
|-----|------|----------|-------------|
| **Life Progress** | 5051 | `/progress` | Year, month, day, life progress percentages with daily quotes |
| **Media Stats** | 5054 | `/api/stats` | Combined Radarr/Sonarr statistics (wanted, downloading, downloaded) |
| **NAS Backup Status** | 9102 | `/status`, `/backups` | PBS backup status with job durations and VM names |
| **NBA Stats** | 5060 | `/games`, `/standings`, `/fantasy` | NBA games, standings, Yahoo Fantasy integration |
| **Docker Stats Exporter** | 9417 | `/metrics` | Prometheus metrics for Docker containers |

## Deployment

All APIs run on `docker-vm-core-utilities01` (192.168.40.13) except:
- Docker Stats Exporter runs on each Docker host (192.168.40.13, 192.168.40.11)

### Deploy via Ansible

```bash
# From ansible controller
cd ~/ansible

# Deploy individual APIs
ansible-playbook glance/deploy-life-progress-api.yml
ansible-playbook glance/deploy-media-stats-api.yml
ansible-playbook glance/deploy-nas-backup-status-api.yml
ansible-playbook glance/deploy-nba-stats-api.yml
ansible-playbook monitoring/deploy-docker-exporter.yml
```

## API Details

### Life Progress API (port 5051)

Calculates time-based progress metrics for the Life Progress widget.

**Environment Variables:**
- `BIRTH_YEAR`, `BIRTH_MONTH`, `BIRTH_DAY` - Birth date
- `TARGET_AGE` - Target lifespan (default: 80)

**Response:**
```json
{
  "year": 4.1,
  "month": 48.3,
  "day": 62.5,
  "life": 35.2,
  "age": 28.3,
  "remaining_years": 51.7,
  "remaining_days": 18879,
  "quote": "Time is the most valuable thing...",
  "target_age": 80
}
```

### Media Stats API (port 5054)

Aggregates Radarr and Sonarr statistics into a single endpoint.

**Environment Variables:**
- `RADARR_URL`, `RADARR_API_KEY`
- `SONARR_URL`, `SONARR_API_KEY`

**Response:**
```json
{
  "stats": [
    {"label": "WANTED MOVIES", "value": 15, "color": "#f59e0b"},
    {"label": "MOVIES DOWNLOADING", "value": 9, "color": "#3b82f6"},
    ...
  ],
  "radarr": {"wanted": 15, "downloading": 9, "downloaded": 850},
  "sonarr": {"wanted": 1906, "downloading": 98, "downloaded": 12500}
}
```

### NAS Backup Status API (port 9102)

Monitors PBS backups and NAS sync status with job durations.

**Endpoints:**
- `/status` - Sync status, job durations, datastore sizes
- `/backups` - List of VMs/CTs with names and last backup times
- `/job-status` - Just the job status portion
- `/health` - Health check with cache status
- `/refresh` - Force cache refresh

**Response (`/status`):**
```json
{
  "status": "success",
  "last_sync": "2026-01-15 02:31:27",
  "nas_sync_duration": "28m 51s",
  "job_status": {
    "daily": {"last_backup": "2026-01-14 18:33", "duration": "3h 39m", "count": 90},
    "main": {"last_backup": "2026-01-14 17:48", "duration": "4h 49m", "count": 57}
  }
}
```

### NBA Stats API (port 5060)

Provides NBA data and Yahoo Fantasy league integration.

**Endpoints:**
- `/games` - Today's NBA games with scores
- `/standings` - Eastern/Western conference standings
- `/injuries` - Injury report with player photos
- `/news` - NBA news headlines
- `/fantasy` - Yahoo Fantasy league standings
- `/fantasy/matchups` - Current week matchups
- `/fantasy/recommendations` - Top available free agents

### Docker Stats Exporter (port 9417)

Prometheus exporter for Docker container metrics.

**Metrics:**
- `docker_container_running` - Container status (1=running)
- `docker_container_cpu_percent` - CPU usage
- `docker_container_memory_percent` - Memory usage
- `docker_container_memory_usage_bytes` - Memory in bytes
- `docker_container_uptime_seconds` - Container uptime

## Testing

```bash
# Life Progress
curl http://192.168.40.13:5051/progress | jq .

# Media Stats
curl http://192.168.40.13:5054/api/stats | jq .

# NAS Backup Status
curl http://192.168.40.13:9102/status | jq .
curl http://192.168.40.13:9102/backups | jq .

# NBA Stats
curl http://192.168.40.13:5060/games | jq .
curl http://192.168.40.13:5060/standings | jq .

# Docker Stats (Prometheus format)
curl http://192.168.40.13:9417/metrics
```

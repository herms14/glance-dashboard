# Glance Dashboard - GitOps Repository

Comprehensive homelab dashboard with 9 tabs covering infrastructure monitoring, media management, backup status, sports, and more.

## Overview

| Property | Value |
|----------|-------|
| **Service** | Glance Dashboard |
| **Version** | 0.7.0+ |
| **Target Host** | docker-lxc-glance (192.168.40.12) |
| **Port** | 8080 |
| **URL** | https://glance.hrmsmrflrii.xyz |

## Dashboard Pages (9 Tabs)

| Tab | Description | Key Widgets |
|-----|-------------|-------------|
| **Home** | Central dashboard with life tracking | Chess.com stats, weather, calendar, daily note, service health monitors, GitHub contributions, life progress |
| **Compute** | Proxmox cluster monitoring | Proxmox Cluster Health (Grafana), Container Status History (Grafana), Linux/Windows VM stats |
| **Storage** | NAS storage metrics | Synology NAS Storage dashboard (Grafana) with RAID status, disk health, temps |
| **Network** | Network infrastructure | Network Utilization (Grafana), Omada Network Overview (Grafana), speedtest |
| **Backup** | PBS backup monitoring | Backup Jobs Overview with durations, VM/CT backup status with names, Drive health, PBS Grafana |
| **Media** | Media server stats | Media Stats grid (Radarr/Sonarr), recent movies, RSS feeds, arr stack bookmarks |
| **Web** | Tech news aggregator | YouTube channels, tech news RSS, AI/ML feeds, cloud/enterprise news, markets |
| **Reddit** | Reddit feed manager | Dynamic multi-subreddit feed with thumbnails, native Reddit widgets |
| **Sports** | NBA and fantasy sports | Today's games, standings, injury report, Yahoo Fantasy league |

## Custom APIs

The dashboard integrates with several custom APIs running on `docker-vm-core-utilities01` (192.168.40.13):

| API | Port | Purpose |
|-----|------|---------|
| Life Progress API | 5051 | Birthday countdown, life milestones |
| Media Stats API | 5054 | Combined Radarr/Sonarr statistics |
| NBA Stats API | 5060 | NBA games, standings, fantasy data |
| Reddit Manager | 5053 | Multi-subreddit feed aggregation |
| NAS Backup Status API | 9102 | PBS backup status with durations and VM names |

## Embedded Grafana Dashboards

| Dashboard | UID | Height | Tab |
|-----------|-----|--------|-----|
| Proxmox Cluster Health | `proxmox-cluster-health` | 3200px | Compute |
| Container Status History | `container-status` | 1250px | Compute |
| Synology NAS Storage | `synology-nas-modern` | 1350px | Storage |
| Network Utilization | `network-utilization` | 1100px | Network |
| Omada Network | `omada-network` | 2200px | Network |
| PBS Backup Status | `pbs-backup-status` | 1400px | Backup |

## Repository Structure

```
glance-homelab/
├── .gitlab-ci.yml          # CI/CD pipeline definition
├── service.yml             # GitOps metadata (target, ports, secrets)
├── config/
│   ├── docker-compose.yml  # Container definition
│   └── glance.yml          # Dashboard configuration (~1800 lines)
├── assets/
│   └── custom-themes.css   # Custom styling (full-width, hidden scrollbars)
├── apis/                   # Custom API source code
│   ├── life-progress-api.py
│   ├── media-stats-api.py
│   ├── nas-backup-status-api.py
│   ├── nba-stats-api.py
│   ├── docker-stats-exporter.py
│   └── README.md
└── README.md
```

## Deployment

### Automatic (GitLab CI/CD)

Push to `main` branch triggers automatic deployment:

1. **Validate** - YAML syntax and Docker Compose validation
2. **Deploy** - Files copied to target host, container updated
3. **Configure** - Traefik route updated for HTTPS access
4. **Verify** - Health check confirms service is running
5. **Notify** - Discord notification sent

### Manual

```bash
# SSH to Glance LXC
ssh root@192.168.40.12

# Update config and restart
cd /opt/glance
docker compose restart
```

## Configuration

### Theme

The dashboard uses a dark theme with full-width display:

```yaml
theme:
  background-color: 15 15 20
  primary-color: 139 92 246
  contrast-multiplier: 1.2
  document-width: 100%
```

### Custom CSS

Full-width display is enabled via `custom-themes.css`:

```css
.content-bounds {
  max-width: 100% !important;
  width: 100% !important;
}
```

## Making Changes

### Edit Dashboard

1. Modify `config/glance.yml`
2. Commit and push to `main`
3. Pipeline deploys automatically

### Add New Service Monitor

Add to the relevant page's monitor widget in `config/glance.yml`:

```yaml
- type: monitor
  sites:
    - title: New Service
      url: https://service.hrmsmrflrii.xyz
      icon: si:iconname
```

### Add Custom API Widget

```yaml
- type: custom-api
  title: Widget Title
  cache: 5m
  url: http://192.168.40.13:PORT/endpoint
  template: |
    <div>{{ .JSON.String "field" }}</div>
```

## CI/CD Variables

### Group Level (homelab group)

| Variable | Description |
|----------|-------------|
| `SSH_PRIVATE_KEY` | SSH key for deployment |
| `DISCORD_WEBHOOK_URL` | Discord notifications |

### Project Level

| Variable | Description |
|----------|-------------|
| `GLANCE_RADARR_API_KEY` | Radarr API key |
| `GLANCE_SONARR_API_KEY` | Sonarr API key |

## Troubleshooting

### Dashboard Not Loading

```bash
# Check container status
ssh root@192.168.40.12 "docker ps -a | grep glance"

# Check container logs
ssh root@192.168.40.12 "docker logs glance --tail 100"

# Restart container
ssh root@192.168.40.12 "cd /opt/glance && docker compose restart"
```

### Widget Showing Error

- Check URL accessibility from the Glance container
- Verify API keys are configured
- Check cache settings (increase if API is slow)

### Grafana Iframe Not Loading

- Verify Grafana is accessible at `https://grafana.hrmsmrflrii.xyz`
- Check dashboard UID matches
- Ensure `kiosk` and `theme=transparent` parameters are set

## Links

- [Glance Documentation](https://github.com/glanceapp/glance)
- [Dashboard URL](https://glance.hrmsmrflrii.xyz)
- [Grafana](https://grafana.hrmsmrflrii.xyz)
- [GitLab Pipeline](https://gitlab.hrmsmrflrii.xyz/homelab/glance-homelab/-/pipelines)

## Recent Updates

### January 15, 2026
- Enhanced Backup page with job durations (daily, main, NAS sync)
- VM/CT backup status now shows names instead of just VMIDs
- Restructured Backup layout with sidebar and main column
- PBS Grafana iframe height increased to 1400px

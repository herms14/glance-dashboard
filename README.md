# Glance Dashboard - GitOps Repository

Comprehensive homelab dashboard with 12 pages featuring emoji navigation icons, 35 themes, and extensive infrastructure monitoring.

## Overview

| Property | Value |
|----------|-------|
| **Service** | Glance Dashboard |
| **Version** | 2.2.0 |
| **Target Host** | docker-lxc-glance (192.168.40.12) |
| **Port** | 8080 |
| **URL** | https://glance.hrmsmrflrii.xyz |
| **Themes** | 35 available |

## Dashboard Pages (12 Tabs)

| Tab | Icon | Description | Key Widgets |
|-----|------|-------------|-------------|
| **Home** | 🏠 | Central dashboard with life tracking | Chess.com stats, Steam top/last played, weather, calendar, GitHub contributions, life progress, power control |
| **Services** | 🛠 | Infrastructure health monitors | Proxmox nodes, PBS server, Synology NAS, Docker containers status |
| **Compute** | 💻 | Proxmox cluster monitoring | Proxmox Cluster Health (Grafana), Container Monitoring (Grafana), Immich Host Health (Grafana), Gaming PC stats |
| **Storage** | 💾 | NAS storage metrics | Synology NAS Storage dashboard (Grafana) with RAID status, disk health, temps |
| **Backup** | 📦 | PBS backup monitoring | Backup Jobs Overview with durations, VM/CT backup status with names, Drive health, PBS Grafana |
| **Network** | 🌐 | Network infrastructure | Network Utilization (Grafana), Omada Network Overview (Grafana), speedtest |
| **Media** | 🎬 | Media server stats | Media Stats grid (Radarr/Sonarr), recent movies, RSS feeds, arr stack bookmarks |
| **News** | 📰 | Tech news aggregator | Hacker News, tech RSS feeds, headline aggregation |
| **Finance** | 💰 | Financial markets | Stock markets, crypto prices, financial widgets |
| **Reddit** | 🤖 | Reddit feed manager | Dynamic multi-subreddit feed with thumbnails, native Reddit widgets |
| **Sports** | 🏀 | NBA and fantasy sports | Today's games, standings, injury report, Yahoo Fantasy league |
| **Health** | 💪 | Fitness tracking with Strava | Weekly exercise, weight progress, Strava stats, exercise calendar, weight chart, recent activities |

## Custom APIs

The dashboard integrates with several custom APIs running on `docker-vm-core-utilities01` (192.168.40.13):

| API | Port | Purpose | Traefik Domain |
|-----|------|---------|----------------|
| Life Progress API | 5051 | Birthday countdown, life milestones | — |
| Steam Stats API | 5055 | Steam profile, top/recent games | — |
| Gaming PC Stats | 5056 | LibreHardwareMonitor data (CPU/GPU/RAM) | — |
| Power Control API | 5057 | Wake-on-LAN, shutdown, backup triggering | `power.hrmsmrflrii.xyz` |
| Media Stats API | 5054 | Combined Radarr/Sonarr statistics | — |
| NBA Stats API | 5060 | NBA games, standings, fantasy data | — |
| Health Tracker API | 5062 | Strava OAuth2, weight logging, exercise tracking | `health-api.hrmsmrflrii.xyz` |
| Reddit Manager | 5053 | Multi-subreddit feed aggregation | — |
| NAS Backup Status API | 9102 | PBS backup status with durations and VM names | — |

## Embedded Grafana Dashboards

| Dashboard | UID | Height | Tab |
|-----------|-----|--------|-----|
| Proxmox Cluster Health | `proxmox-cluster-health` | 2400px | Compute |
| Container Monitoring | `containers-modern` | 1800px | Compute |
| Immich Host Health | `immich-host-health` | 900px | Compute |
| Synology NAS Storage | `synology-nas-modern` | 1350px | Storage |
| Network Utilization | `network-utilization` | 1100px | Network |
| Omada Network | `omada-network` | 2200px | Network |
| PBS Backup Status | `pbs-backup-status` | 1000px | Backup |

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
│   ├── docker-stats-exporter.py
│   ├── health-tracker-api.py
│   ├── life-progress-api.py
│   ├── media-stats-api.py
│   ├── nas-backup-status-api.py
│   ├── nba-stats-api.py
│   ├── power-control-api.py
│   ├── steam-stats-api.py
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

### Iframe Not Loading (Mixed Content)

- Glance is served over HTTPS — all iframe `source:` URLs must also be HTTPS
- HTTP iframes will be silently blocked by the browser (mixed content)
- Solution: Route APIs through Traefik with HTTPS (e.g., `health-api.hrmsmrflrii.xyz`, `power.hrmsmrflrii.xyz`)
- Note: Glance iframe widgets use `source:` (not `url:`). Using `url:` causes "source is required" errors

### Grafana Iframe Not Loading

- Verify Grafana is accessible at `https://grafana.hrmsmrflrii.xyz`
- Check dashboard UID matches
- Ensure `kiosk` and `theme=transparent` parameters are set

### Custom API Timeout Error

- If a custom-api widget shows "context deadline exceeded", the upstream API is too slow
- Glance has a ~5 second HTTP timeout for custom-api widgets
- Fix: Reduce connection timeouts in the API (e.g., gaming-pc-stats uses 2s timeout for offline hosts)

## Links

- [Glance Documentation](https://github.com/glanceapp/glance)
- [Dashboard URL](https://glance.hrmsmrflrii.xyz)
- [Grafana](https://grafana.hrmsmrflrii.xyz)
- [GitLab Pipeline](https://gitlab.hrmsmrflrii.xyz/homelab/glance-homelab/-/pipelines)

## Available Themes (35)

The dashboard includes 35 color themes:

**Original Themes:** deep-purple, purple-rain, dark-modern, charcoal, midnight-blue, forest-green, ocean-blue, sunset, nord, dracula

**Editor Themes:** one-dark, material-ocean, ayu-dark, ayu-mirage, synthwave-84, night-owl, palenight, horizon, everforest

**Rose Pine:** rose-pine, rose-pine-moon

**Catppuccin:** catppuccin-macchiato, catppuccin-frappe

**GitHub:** github-dark, github-dimmed

**Modern:** kanagawa, vesper, poimandres, vitesse-dark, oxocarbon, mellow, aurora, fairy-floss

**Terminal:** blue-matrix, green-matrix, amber-terminal, high-contrast

## Recent Updates

See [CHANGELOG.md](CHANGELOG.md) for full version history.

### v2.2.0 (February 16, 2026) - Health & Fitness Page
- **New Health page** (12th tab) with Strava integration and weight tracking
- Health Tracker API (port 5062) with Strava OAuth2, activity caching, weight logging
- Strava Stats dashboard: Last 4 Weeks, Best Efforts, Year to Date, All-Time
- Exercise Calendar: 60-day GitHub-style heatmap
- Weight Tracker: Chart.js line chart with goal line and logging form
- Weekly Exercise summary with rolling 7-day active days count
- HTTPS routing via Traefik (`health-api.hrmsmrflrii.xyz`)
- **Home page improvements**: Steam "Last Played" game, Power Control via HTTPS
- **Compute page fix**: Gaming PC widget timeout reduced (2s instead of 5s)
- Added Immich Host Health Grafana dashboard to Compute page

### v2.1.0 (January 20, 2026) - Power Control Panel
- Added Power Control widget on Home page with interactive buttons
- Wake-on-LAN, Shutdown, and Backup Now functionality
- Real-time node status indicators
- Power Control API (port 5057) with embedded web UI

### v2.0.0 (January 20, 2026) - Major UI Redesign
- Added page icons/emojis for all 11 pages
- Created new Services page consolidating health monitors
- Split Web page into News and Finance
- Added 25 new themes (now 35 total)
- Standardized widget styling (padding: 12px, border-radius: 8px)
- Optimized iframe heights

### v1.5.0 (January 15, 2026)
- Enhanced Backup page with job durations (daily, main, NAS sync)
- VM/CT backup status now shows names instead of just VMIDs
- Restructured Backup layout with sidebar and main column
- PBS Grafana iframe height increased to 1400px

# Changelog

All notable changes to the Glance Dashboard will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [4.1.0] - 2026-10-18

### Added
- Network page: **Technitium DNS (primary)** widget (queries, blocked, cached, clients, SERVFAIL, NXDOMAIN for the last hour) through the Technitium API with a read-only token (`GLANCE_TECHNITIUM_TOKEN`); Technitium in Service Status and Quick Links.

### Changed
- Pi-hole widget renamed **Pi-hole DNS (secondary)**.

## [4.0.0] - 2026-10-18

### Changed
- Redesigned dashboard, live since 2026-10-18: `config/glance.yml` holds theme and branding and includes one file per page from `config/pages/`.
- New styling `assets/lab.css` (warm-amber theme, KPI tiles, status colours, phone layout); `custom-themes.css` is no longer referenced.
- Static infrastructure, NAS, drive, RAID and VLAN text replaced by live data from Lab Feed (`:8790` on the Roundtable host).
- Latency merged into one Internet widget; Reddit feeds merged into multireddits; Compute excludes templates; duplicate Grafana iframe removed from Storage.
- Environment variables renamed: `GLANCE_PVE_AUTH`, `GLANCE_RADARR_KEY`, `GLANCE_SONARR_KEY`, `GLANCE_PROWLARR_KEY`, plus new `LABFEED_TOKEN`.
- `docker-compose.yml`: `TZ=Asia/Manila`.

### Added
- Roundtable page (approvals, timers, AI spend, team, activity, open issues).

### Security
- The Services page no longer embeds the Service Version Manager update key; Update files a Roundtable approval through Lab Feed. `SERVICE_VERSION_API_KEY` removed from `.env.example`.

## [3.0.0] - 2026-10-06

### Changed
- Re-synced `config/glance.yml`, `config/docker-compose.yml` and `assets/custom-themes.css` from the live host (`docker-lxc-glance`, CT200).
- Dashboard is now 8 pages: Home, Services, Compute, Storage, Backup, Network, Media, News.
- Secrets in `glance.yml` replaced with `${PROXMOX_API_TOKEN}`, `${RADARR_API_KEY}`, `${SONARR_API_KEY}`, `${PROWLARR_API_KEY}`, `${SERVICE_VERSION_API_KEY}`; added `config/.env.example`.
- `apis/` restructured to one folder per API with its live Dockerfile and compose file.
- `life-progress` reads `BIRTH_DATE`/`TARGET_AGE` from the environment; `pihole-stats-api` reads `PIHOLE_PASSWORD`; `steam-stats` and `service-version-api` take keys from `.env`.
- README rewritten for the current setup; GitLab pipeline documented as legacy.

### Added
- `apis/service-version-api` (5070): service health, versions and one-click updates for the Services page.
- `apis/pihole-stats-api` (5055 on CT200) and `apis/proxmox-nodes-api` (5061 on CT200).

### Removed
- Finance, Reddit, Sports and Health pages (removed live on 2026-08-29).
- Power control panel from Home.
- health-tracker, nba-stats, media-stats, docker-stats-exporter and power-control APIs moved to `apis/_retired/`.
## [2.1.0] - 2026-01-20

### Added
- **Power Control Panel** on Home page with interactive buttons:
  - ⚡ Wake All - Send Wake-on-LAN to all 3 Proxmox nodes
  - 🔴 Shutdown - Graceful shutdown of all nodes (with confirmation modal)
  - 📦 Backup Now - Trigger daily backup job immediately
- Real-time node status indicators (online/offline)
- Power Control API (port 5057) with embedded web UI
- Async operation handling with status polling

## [2.0.0] - 2026-01-20

### Added
- Page icons/emojis for all 11 pages for improved navigation
  - 🏠 Home, 🛠 Services, 💻 Compute, 💾 Storage, 📦 Backup
  - 🌐 Network, 🎬 Media, 📰 News, 💰 Finance, 🤖 Reddit, 🏀 Sports
- New **Services** page consolidating all infrastructure health monitors
  - Proxmox nodes health status
  - PBS server health
  - Synology NAS status
  - Docker containers status (Utilities and Media VMs)
- **News** page (split from Web) - Hacker News, tech RSS feeds
- **Finance** page (split from Web) - Stock markets, crypto prices
- 25 new color themes (total now 35):
  - Editor themes: one-dark, material-ocean, ayu-dark, ayu-mirage, synthwave-84, night-owl, palenight, horizon, everforest
  - Rose Pine variants: rose-pine, rose-pine-moon
  - Japanese aesthetics: kanagawa
  - Catppuccin: catppuccin-macchiato, catppuccin-frappe
  - GitHub: github-dark, github-dimmed
  - Modern: vesper, poimandres, vitesse-dark, oxocarbon, mellow, aurora, fairy-floss
  - Terminal: blue-matrix, green-matrix, amber-terminal, high-contrast

### Changed
- Standardized widget styling across all pages
  - Consistent padding: 12px (previously varied 8-15px)
  - Consistent border-radius: 8px (previously varied 6-12px)
- Optimized iframe heights for better viewport utilization
  - Proxmox Cluster Health: 3200px → 2400px
  - Container Status History: 2500px → 1800px
- Improved cache times for efficiency
  - Life Progress widget: 1h → 6h
  - GitHub contribution graph: 6h → 12h

### Fixed
- Backup schedule text corrected to match actual PBS schedules
  - Daily backup: 21:00 → 19:00 (7 PM)
  - Main backup: midnight → 02:00 AM

### Removed
- Duplicate health monitors from Home page (moved to Services page)
- Web page (split into News and Finance pages)

## [1.5.0] - 2026-01-15

### Added
- Job durations display for backup jobs (daily, main, NAS sync)
- VM/CT names in backup status widget (previously just VMIDs)
- New `/job-status` API endpoint for backup job status
- New `/refresh` API endpoint to force cache refresh

### Changed
- Restructured Backup page layout with sidebar and main column
- PBS Grafana iframe height increased to 1400px
- NAS Backup Status API response now includes duration formatting

## [1.4.0] - 2026-01-14

### Added
- Linux/Windows VM separation in Proxmox Cluster Health dashboard
- VM count panels with color coding (Linux: orange, Windows: blue)
- Enhanced status timelines with height 10 for better readability

### Fixed
- "Not Backed Up" count query (changed from sum to max to avoid node duplication)

## [1.3.0] - 2026-01-13

### Added
- Network Utilization Grafana dashboard
- Cluster bandwidth monitoring with 1Gbps reference line
- Synology NAS bandwidth monitoring (eth0/eth1)
- Steam Top Played widget on Home page
- Gaming PC Stats widget on Compute page

## [1.2.0] - 2026-01-11

### Added
- Proxmox Cluster Health Grafana dashboard
- CPU temperature monitoring (3 nodes)
- Storage pool usage visualization
- VM status timelines

## [1.1.0] - 2026-01-08

### Added
- RAID Status panels to Synology NAS dashboard
- SSD Cache Status monitoring
- Disk temperature tracking for all 6 drives

### Changed
- Memory gauge now excludes cache/buffers for accurate usage

## [1.0.0] - 2026-01-05

### Added
- Initial release with 9 dashboard pages
- Home, Compute, Storage, Network, Backup, Media, Web, Reddit, Sports
- Custom APIs: Life Progress, Media Stats, NBA Stats, Reddit Manager
- Embedded Grafana dashboards
- GitLab CI/CD deployment pipeline
- 10 color themes

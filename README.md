# Glance Dashboard - GitOps Repository

Homelab dashboard with service monitoring, media stats, weather, and more.

## Overview

| Property | Value |
|----------|-------|
| **Service** | Glance Dashboard |
| **Version** | 0.7.0+ |
| **Target Host** | docker-lxc-glance (192.168.40.12) |
| **Port** | 8080 |
| **URL** | https://glance.hrmsmrflrii.xyz |

## Deployment

This repository is automatically deployed via GitLab CI/CD when changes are pushed to the `main` branch.

### What Happens on Push

1. **Validate** - YAML syntax and Docker Compose validation
2. **Deploy** - Files copied to target host, container updated
3. **Configure** - Traefik route updated for HTTPS access
4. **Verify** - Health check confirms service is running
5. **Notify** - Discord notification sent

## Repository Structure

```
glance-homelab/
├── .gitlab-ci.yml          # CI/CD pipeline definition
├── service.yml             # GitOps metadata (target, ports, secrets)
├── config/
│   ├── docker-compose.yml  # Container definition
│   └── glance.yml          # Dashboard configuration
├── assets/
│   └── custom-themes.css   # Custom styling
└── README.md
```

## Configuration

### Dashboard Pages

| Page | Content |
|------|---------|
| **Home** | Clock, weather, service health, bookmarks, markets, RSS feeds |
| **Media** | Media service status (*arr stack), quick links |
| **Network** | Network device monitoring (switches, router, firewall) |
| **Storage** | Synology NAS dashboard (Grafana iframe) |
| **Containers** | Container status history (Grafana iframe) |

### Theme Presets

Available themes (selectable via theme picker icon):
- Catppuccin Mocha (default)
- Midnight Blue
- Nord
- Dracula
- Tokyo Night

## Making Changes

### Edit Dashboard Configuration

1. Modify `config/glance.yml`
2. Commit and push to `main`
3. Pipeline deploys automatically

### Add New Bookmarks

Edit `config/glance.yml` under the relevant page's bookmarks widget.

### Add New Service Monitor

Edit `config/glance.yml` under the relevant page's monitor widget.

### Change Theme

Edit `config/glance.yml` under the `theme:` section.

## Required CI/CD Variables

### Group Level (homelab group)

| Variable | Description |
|----------|-------------|
| `SSH_PRIVATE_KEY` | SSH key for deployment |
| `DISCORD_WEBHOOK_URL` | Discord notifications |

### Project Level

| Variable | Description |
|----------|-------------|
| `GLANCE_RADARR_API_KEY` | Radarr API key for media stats |
| `GLANCE_SONARR_API_KEY` | Sonarr API key for media stats |
| `GLANCE_OPNSENSE_CREDENTIALS` | OPNsense API credentials (base64) |

## Manual Operations

### Rollback

Trigger the `rollback` job manually in GitLab CI/CD to revert to the previous configuration.

### Restart

Trigger the `restart` job manually to restart the container without redeploying.

## Troubleshooting

### Dashboard Not Loading

```bash
# Check container status
ssh root@192.168.40.12 "docker ps -a | grep glance"

# Check container logs
ssh root@192.168.40.12 "docker logs glance --tail 100"
```

### Widget Showing Error

Check the specific widget configuration in `config/glance.yml`. Common issues:
- Invalid URL for monitor sites
- Missing API key for media widgets
- Network connectivity to monitored services

### Pipeline Failed

Check the pipeline logs in GitLab. Common issues:
- SSH key not configured
- Target host unreachable
- YAML syntax error

## Links

- [Glance Documentation](https://github.com/glanceapp/glance)
- [GitLab Pipeline](https://gitlab.hrmsmrflrii.xyz/homelab/glance-homelab/-/pipelines)
- [Dashboard URL](https://glance.hrmsmrflrii.xyz)

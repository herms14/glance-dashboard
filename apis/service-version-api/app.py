#!/usr/bin/env python3
"""
Service Version Manager API
Tracks Docker container health, versions, and provides one-click updates.
Designed for Glance dashboard custom-api widgets.
"""

import subprocess
import json
import os
import re
import time
import uuid
import threading
import atexit
import logging
from datetime import datetime
from flask import Flask, jsonify, request, redirect
from flask_cors import CORS

try:
    import requests as http_requests
except ImportError:
    http_requests = None

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ============================================================
# Configuration
# ============================================================

SSH_KEY = "/root/.ssh/homelab_ed25519"
SSH_USER = "hermes-admin"
SSH_OPTS = f"-i {SSH_KEY} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=5 -o BatchMode=yes"
UPDATE_API_KEY = os.environ.get("UPDATE_API_KEY", "change-me")

# Services that CANNOT be updated via one-click (critical infrastructure)
UPDATE_BLACKLIST = {"traefik", "authentik-server", "authentik-worker", "glance"}

# Cache TTLs (seconds)
HEALTH_CACHE_TTL = 60       # 1 minute
VERSION_CACHE_TTL = 3600    # 1 hour
REGISTRY_CACHE_TTL = 21600  # 6 hours

# Background refresh intervals
HEALTH_REFRESH_INTERVAL = 55
VERSION_REFRESH_INTERVAL = 3600

# ============================================================
# Service Registry
# ============================================================

SERVICE_REGISTRY = {
    # --- Infrastructure (HTTP health-check only, no Docker version) ---
    "node01": {
        "display_name": "Node 01",
        "category": "infrastructure",
        "icon": "proxmox",
        "type": "http_only",
        "health_url": "https://192.168.20.20:8006",
        "health_insecure": True,
        "web_url": "https://proxmox.hrmsmrflrii.xyz",
    },
    "node02": {
        "display_name": "Node 02",
        "category": "infrastructure",
        "icon": "proxmox",
        "type": "http_only",
        "health_url": "https://192.168.20.21:8006",
        "health_insecure": True,
        "web_url": "https://proxmox.hrmsmrflrii.xyz",
    },
    "node03": {
        "display_name": "Node 03",
        "category": "infrastructure",
        "icon": "proxmox",
        "type": "http_only",
        "health_url": "https://192.168.20.22:8006",
        "health_insecure": True,
        "web_url": "https://proxmox.hrmsmrflrii.xyz",
    },
    "synology-nas": {
        "display_name": "Synology NAS",
        "category": "infrastructure",
        "icon": "synology",
        "type": "http_only",
        "health_url": "https://192.168.20.32:5001",
        "health_insecure": True,
        "web_url": "https://192.168.20.32:5001",
    },
    "pbs": {
        "display_name": "PBS Server",
        "category": "infrastructure",
        "icon": "proxmox-backup-server",
        "type": "http_only",
        "health_url": "https://192.168.20.50:8007",
        "health_insecure": True,
        "web_url": "https://pbs.hrmsmrflrii.xyz",
    },
    "traefik": {
        "display_name": "Traefik",
        "category": "infrastructure",
        "icon": "traefik",
        "host_ip": "192.168.40.20",
        "compose_dir": "/opt/traefik",
        "container_name": "traefik",
        "health_url": "http://192.168.40.20:8082/ping",
        "web_url": "https://traefik.hrmsmrflrii.xyz",
    },

    # --- Auth & Identity ---
    "authentik-server": {
        "display_name": "Authentik",
        "category": "auth",
        "icon": "authentik",
        "host_ip": "192.168.40.21",
        "compose_dir": "/opt/authentik",
        "container_name": "authentik-server",
        "health_url": "http://192.168.40.21:9000/-/health/ready/",
        "web_url": "https://auth.hrmsmrflrii.xyz",
    },
    "authentik-worker": {
        "display_name": "Authentik Worker",
        "category": "auth",
        "icon": "authentik",
        "host_ip": "192.168.40.21",
        "compose_dir": "/opt/authentik",
        "container_name": "authentik-worker",
        "health_url": None,
        "web_url": "https://auth.hrmsmrflrii.xyz",
    },
    "pihole": {
        "display_name": "Pi-hole",
        "category": "auth",
        "icon": "pi-hole",
        "type": "http_only",
        "health_url": "https://pihole.hrmsmrflrii.xyz/admin/",
        "health_insecure": True,
        "web_url": "https://pihole.hrmsmrflrii.xyz/admin/",
    },

    # --- Core Applications ---
    "gitlab": {
        "display_name": "GitLab",
        "category": "core_apps",
        "icon": "gitlab",
        "host_ip": "192.168.40.23",
        "compose_dir": "/opt/gitlab",
        "container_name": "gitlab",
        "health_url": "http://192.168.40.23:80/users/sign_in",
        "web_url": "https://gitlab.hrmsmrflrii.xyz",
    },
    "immich-server": {
        "display_name": "Immich",
        "category": "core_apps",
        "icon": "immich",
        "host_ip": "192.168.40.22",
        "compose_dir": "/opt/immich",
        "container_name": "immich-server",
        "health_url": "http://192.168.40.22:2283/api/server/ping",
        "web_url": "https://photos.hrmsmrflrii.xyz",
    },
    "immich-ml": {
        "display_name": "Immich ML",
        "category": "core_apps",
        "icon": "immich",
        "host_ip": "192.168.40.22",
        "compose_dir": "/opt/immich",
        "container_name": "immich-ml",
        "health_url": None,
        "web_url": "https://photos.hrmsmrflrii.xyz",
    },
    "n8n": {
        "display_name": "n8n",
        "category": "core_apps",
        "icon": "n8n",
        "host_ip": "192.168.40.13",
        "compose_dir": "/opt/monitoring",
        "container_name": "n8n",
        "health_url": "http://192.168.40.13:5678/healthz",
        "web_url": "https://n8n.hrmsmrflrii.xyz",
    },
    "paperless": {
        "display_name": "Paperless",
        "category": "core_apps",
        "icon": "paperless-ngx",
        "host_ip": "192.168.40.13",
        "compose_dir": "/opt/paperless",
        "container_name": "paperless",
        "health_url": "http://192.168.40.13:8000",
        "web_url": "https://paperless.hrmsmrflrii.xyz",
    },
    "karakeep": {
        "display_name": "Karakeep",
        "category": "core_apps",
        "icon": "linkwarden",
        "host_ip": "192.168.40.13",
        "compose_dir": "/opt/karakeep",
        "container_name": "karakeep",
        "health_url": "http://192.168.40.13:3005",
        "web_url": "https://karakeep.hrmsmrflrii.xyz",
    },
    "lagident": {
        "display_name": "Lagident",
        "category": "core_apps",
        "icon": "photoprism",
        "host_ip": "192.168.40.13",
        "compose_dir": "/opt/lagident",
        "container_name": "lagident",
        "health_url": "http://192.168.40.13:9933",
        "web_url": "https://lagident.hrmsmrflrii.xyz",
    },
    "homeassistant": {
        "display_name": "Home Assistant",
        "category": "core_apps",
        "icon": "home-assistant",
        "host_ip": "192.168.40.25",
        "compose_dir": "/opt/homeassistant",
        "container_name": "homeassistant",
        "health_url": "http://192.168.40.25:8123",
        "web_url": "http://192.168.40.25:8123",
    },
    "ghostfolio": {
        "display_name": "Ghostfolio",
        "category": "core_apps",
        "icon": "ghostfolio",
        "host_ip": "192.168.40.26",
        "compose_dir": "/opt/ghostfolio",
        "container_name": "ghostfolio",
        "health_url": "http://192.168.40.26:3333",
        "web_url": "https://ghostfolio.hrmsmrflrii.xyz",
    },
    "reactive-resume": {
        "display_name": "Reactive Resume",
        "category": "core_apps",
        "icon": "reactive-resume",
        "host_ip": "192.168.40.13",
        "compose_dir": "/opt/reactive-resume",
        "container_name": "reactive-resume",
        "health_url": "http://192.168.40.13:5057",
        "web_url": "https://resume.hrmsmrflrii.xyz",
    },
    "bentopdf": {
        "display_name": "BentoPDF",
        "category": "core_apps",
        "icon": "stirling-pdf",
        "host_ip": "192.168.40.13",
        "compose_dir": "/opt/bentopdf",
        "container_name": "bentopdf",
        "health_url": "http://192.168.40.13:5055",
        "web_url": "https://bentopdf.hrmsmrflrii.xyz",
    },
    "open-notebook": {
        "display_name": "Open Notebook",
        "category": "core_apps",
        "icon": "jupyter",
        "host_ip": "192.168.40.13",
        "compose_dir": "/opt/open-notebook",
        "container_name": "open-notebook",
        "health_url": "http://192.168.40.13:5059",
        "web_url": "http://192.168.40.13:5059",
    },

    # --- Media Stack ---
    "jellyfin": {
        "display_name": "Jellyfin",
        "category": "media",
        "icon": "jellyfin",
        "host_ip": "192.168.40.11",
        "compose_dir": "/opt/arr-stack",
        "container_name": "jellyfin",
        "health_url": "http://192.168.40.11:8096/health",
        "web_url": "https://jellyfin.hrmsmrflrii.xyz",
    },
    "radarr": {
        "display_name": "Radarr",
        "category": "media",
        "icon": "radarr",
        "host_ip": "192.168.40.11",
        "compose_dir": "/opt/arr-stack",
        "container_name": "radarr",
        "health_url": "http://192.168.40.11:7878/ping",
        "web_url": "https://radarr.hrmsmrflrii.xyz",
    },
    "sonarr": {
        "display_name": "Sonarr",
        "category": "media",
        "icon": "sonarr",
        "host_ip": "192.168.40.11",
        "compose_dir": "/opt/arr-stack",
        "container_name": "sonarr",
        "health_url": "http://192.168.40.11:8989/ping",
        "web_url": "https://sonarr.hrmsmrflrii.xyz",
    },
    "lidarr": {
        "display_name": "Lidarr",
        "category": "media",
        "icon": "lidarr",
        "host_ip": "192.168.40.11",
        "compose_dir": "/opt/arr-stack",
        "container_name": "lidarr",
        "health_url": "http://192.168.40.11:8686/ping",
        "web_url": "https://lidarr.hrmsmrflrii.xyz",
    },
    "prowlarr": {
        "display_name": "Prowlarr",
        "category": "media",
        "icon": "prowlarr",
        "host_ip": "192.168.40.11",
        "compose_dir": "/opt/arr-stack",
        "container_name": "prowlarr",
        "health_url": "http://192.168.40.11:9696/ping",
        "web_url": "https://prowlarr.hrmsmrflrii.xyz",
    },
    "bazarr": {
        "display_name": "Bazarr",
        "category": "media",
        "icon": "bazarr",
        "host_ip": "192.168.40.11",
        "compose_dir": "/opt/arr-stack",
        "container_name": "bazarr",
        "health_url": "http://192.168.40.11:6767/ping",
        "web_url": "https://bazarr.hrmsmrflrii.xyz",
    },
    "jellyseerr": {
        "display_name": "Jellyseerr",
        "category": "media",
        "icon": "jellyseerr",
        "host_ip": "192.168.40.11",
        "compose_dir": "/opt/arr-stack",
        "container_name": "jellyseerr",
        "health_url": "http://192.168.40.11:5056",
        "web_url": "https://jellyseerr.hrmsmrflrii.xyz",
    },
    "overseerr": {
        "display_name": "Overseerr",
        "category": "media",
        "icon": "overseerr",
        "host_ip": "192.168.40.11",
        "compose_dir": "/opt/arr-stack",
        "container_name": "overseerr",
        "health_url": "http://192.168.40.11:5055",
        "web_url": "https://overseerr.hrmsmrflrii.xyz",
    },
    "tdarr": {
        "display_name": "Tdarr",
        "category": "media",
        "icon": "tdarr",
        "host_ip": "192.168.40.11",
        "compose_dir": "/opt/arr-stack",
        "container_name": "tdarr",
        "health_url": "http://192.168.40.11:8265",
        "web_url": "http://192.168.40.11:8265",
    },
    "autobrr": {
        "display_name": "Autobrr",
        "category": "media",
        "icon": "autobrr",
        "host_ip": "192.168.40.11",
        "compose_dir": "/opt/arr-stack",
        "container_name": "autobrr",
        "health_url": "http://192.168.40.11:7474",
        "web_url": "http://192.168.40.11:7474",
    },
    "deluge": {
        "display_name": "Deluge",
        "category": "media",
        "icon": "deluge",
        "host_ip": "192.168.40.11",
        "compose_dir": "/opt/arr-stack",
        "container_name": "deluge",
        "health_url": "http://192.168.40.11:8112",
        "web_url": "http://192.168.40.11:8112",
    },
    "sabnzbd": {
        "display_name": "SABnzbd",
        "category": "media",
        "icon": "sabnzbd",
        "host_ip": "192.168.40.11",
        "compose_dir": "/opt/arr-stack",
        "container_name": "sabnzbd",
        "health_url": "http://192.168.40.11:8081",
        "web_url": "http://192.168.40.11:8081",
    },
    "metube": {
        "display_name": "MeTube",
        "category": "media",
        "icon": "metube",
        "host_ip": "192.168.40.11",
        "compose_dir": "/opt/metube",
        "container_name": "metube",
        "health_url": "http://192.168.40.11:8082",
        "web_url": "http://192.168.40.11:8082",
    },
    "wizarr": {
        "display_name": "Wizarr",
        "category": "media",
        "icon": "wizarr",
        "host_ip": "192.168.40.13",
        "compose_dir": "/opt/wizarr",
        "container_name": "wizarr",
        "health_url": "http://192.168.40.13:5690",
        "web_url": "https://wizarr.hrmsmrflrii.xyz",
    },
    "tracearr": {
        "display_name": "Tracearr",
        "category": "media",
        "icon": "tautulli",
        "host_ip": "192.168.40.13",
        "compose_dir": "/opt/tracearr",
        "container_name": "tracearr",
        "health_url": "http://192.168.40.13:3002",
        "web_url": "https://tracearr.hrmsmrflrii.xyz",
    },

    # --- Monitoring & Observability ---
    "grafana": {
        "display_name": "Grafana",
        "category": "monitoring",
        "icon": "grafana",
        "host_ip": "192.168.40.13",
        "compose_dir": "/opt/monitoring",
        "container_name": "grafana",
        "health_url": "https://grafana.hrmsmrflrii.xyz/api/health",
        "web_url": "https://grafana.hrmsmrflrii.xyz",
    },
    "prometheus": {
        "display_name": "Prometheus",
        "category": "monitoring",
        "icon": "prometheus",
        "host_ip": "192.168.40.13",
        "compose_dir": "/opt/monitoring",
        "container_name": "prometheus",
        "health_url": "http://192.168.40.13:9090/-/healthy",
        "web_url": "https://prometheus.hrmsmrflrii.xyz",
    },
    "uptime-kuma": {
        "display_name": "Uptime Kuma",
        "category": "monitoring",
        "icon": "uptime-kuma",
        "host_ip": "192.168.40.13",
        "compose_dir": "/opt/monitoring",
        "container_name": "uptime-kuma",
        "health_url": "http://192.168.40.13:3001",
        "web_url": "https://uptime.hrmsmrflrii.xyz",
    },
    "speedtest-tracker": {
        "display_name": "Speedtest",
        "category": "monitoring",
        "icon": "speedtest-tracker",
        "host_ip": "192.168.40.13",
        "compose_dir": "/opt/monitoring",
        "container_name": "speedtest-tracker",
        "health_url": "http://192.168.40.13:3000/api/healthcheck",
        "web_url": "https://speedtest.hrmsmrflrii.xyz",
    },
    "jaeger": {
        "display_name": "Jaeger",
        "category": "monitoring",
        "icon": "jaeger",
        "host_ip": "192.168.40.13",
        "compose_dir": "/opt/monitoring",
        "container_name": "jaeger",
        "health_url": "http://192.168.40.13:16686",
        "web_url": "https://jaeger.hrmsmrflrii.xyz",
    },
    "glance": {
        "display_name": "Glance",
        "category": "monitoring",
        "icon": "glance",
        "host_ip": "192.168.40.12",
        "compose_dir": "/opt/glance",
        "container_name": "glance",
        "health_url": "http://192.168.40.12:8080",
        "web_url": "https://glance.hrmsmrflrii.xyz",
    },
    "cadvisor": {
        "display_name": "cAdvisor",
        "category": "monitoring",
        "icon": "cadvisor",
        "host_ip": "192.168.40.13",
        "compose_dir": "/opt/monitoring",
        "container_name": "cadvisor",
        "health_url": "http://192.168.40.13:8081",
        "web_url": "http://192.168.40.13:8081",
    },

    # --- Custom APIs & Bots (local builds, health only) ---
    "sentinel-bot": {
        "display_name": "Sentinel Bot",
        "category": "apis_bots",
        "icon": "discord",
        "host_ip": "192.168.40.13",
        "compose_dir": "/opt/sentinel-bot",
        "container_name": "sentinel-bot",
        "registry": "local",
        "health_url": "http://192.168.40.13:5050/health",
        "web_url": None,
    },
    "media-stats-api": {
        "display_name": "Media Stats API",
        "category": "apis_bots",
        "icon": "radarr",
        "host_ip": "192.168.40.12",
        "compose_dir": "/opt/glance",
        "container_name": "media-stats-api",
        "registry": "local",
        "health_url": "http://192.168.40.12:5054/health",
        "web_url": None,
    },
    "nas-backup-api": {
        "display_name": "NAS Backup API",
        "category": "apis_bots",
        "icon": "synology",
        "host_ip": "192.168.40.13",
        "compose_dir": "/opt/nas-backup-status-api",
        "container_name": "nas-backup-status-api",
        "registry": "local",
        "health_url": "http://192.168.40.13:9102/health",
        "web_url": None,
    },
    "reddit-manager": {
        "display_name": "Reddit Manager",
        "category": "apis_bots",
        "icon": "reddit",
        "host_ip": "192.168.40.12",
        "compose_dir": "/opt/glance",
        "container_name": "reddit-manager",
        "registry": "local",
        "health_url": "http://192.168.40.12:5053/health",
        "web_url": None,
    },
    "nba-stats-api": {
        "display_name": "NBA Stats API",
        "category": "apis_bots",
        "icon": "espn",
        "host_ip": "192.168.40.12",
        "compose_dir": "/opt/glance",
        "container_name": "nba-stats-api",
        "registry": "local",
        "health_url": "http://192.168.40.12:5060/health",
        "web_url": None,
    },
    "power-control-api": {
        "display_name": "Power Control",
        "category": "apis_bots",
        "icon": "home-assistant",
        "host_ip": "192.168.40.13",
        "compose_dir": "/opt/power-control-api",
        "container_name": "power-control-api",
        "registry": "local",
        "health_url": "http://192.168.40.13:5057/health",
        "web_url": None,
    },
    "steam-stats": {
        "display_name": "Steam Stats",
        "category": "apis_bots",
        "icon": "steam",
        "host_ip": "192.168.40.13",
        "compose_dir": "/opt/steam-stats",
        "container_name": "steam-stats",
        "registry": "local",
        "health_url": "http://192.168.40.13:5055/health",
        "web_url": None,
    },
    "life-progress": {
        "display_name": "Life Progress",
        "category": "apis_bots",
        "icon": "grafana",
        "host_ip": "192.168.40.13",
        "compose_dir": "/opt/life-progress",
        "container_name": "life-progress",
        "registry": "local",
        "health_url": "http://192.168.40.13:5051/health",
        "web_url": None,
    },
}

# Category display names and order
CATEGORIES = {
    "infrastructure": "Critical Infrastructure",
    "auth": "Auth & Identity",
    "core_apps": "Core Applications",
    "media": "Media Stack",
    "monitoring": "Monitoring & Observability",
    "apis_bots": "Custom APIs & Bots",
}

# ============================================================
# Cache
# ============================================================

cache = {
    "health": {},       # service_name -> {"status": "online"/"offline", "timestamp": float}
    "versions": {},     # service_name -> {"current": str, "current_digest": str, "latest_digest": str, "update_available": bool, "timestamp": float}
    "registry": {},     # image_ref -> {"digest": str, "timestamp": float}
}
cache_lock = threading.Lock()

# Update tasks
update_tasks = {}  # task_id -> {"status", "service", "started", "output", "completed"}
update_locks = {}  # service_name -> threading.Lock()

# Background thread control
stop_event = threading.Event()


# ============================================================
# SSH Utility
# ============================================================

def run_ssh_command(host_ip, cmd, user=None, timeout=30):
    """Run command on a remote host via SSH. Returns (stdout, return_code)."""
    if user is None:
        user = SSH_USER
    full_cmd = f"ssh {SSH_OPTS} {user}@{host_ip} {cmd}"
    try:
        result = subprocess.run(
            full_cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip(), result.returncode
    except subprocess.TimeoutExpired:
        logger.warning(f"SSH timeout: {host_ip} cmd={cmd[:60]}")
        return "", -1
    except Exception as e:
        logger.error(f"SSH error: {host_ip} - {e}")
        return "", -1


# ============================================================
# Health Checking
# ============================================================

def check_health(service_name, service_cfg):
    """Check if a service is healthy via HTTP or Docker inspect."""
    health_url = service_cfg.get("health_url")

    # If no health URL, check Docker container status
    if not health_url:
        host_ip = service_cfg.get("host_ip")
        container = service_cfg.get("container_name")
        if host_ip and container:
            stdout, rc = run_ssh_command(
                host_ip,
                f"'docker inspect --format={{{{.State.Status}}}} {container} 2>/dev/null'"
            )
            return "online" if stdout == "running" else "offline"
        return "unknown"

    # HTTP health check
    if http_requests:
        try:
            verify = not service_cfg.get("health_insecure", False)
            resp = http_requests.get(health_url, timeout=5, verify=verify, allow_redirects=True)
            return "online" if resp.status_code < 500 else "offline"
        except Exception:
            return "offline"
    else:
        # Fallback: curl via subprocess
        insecure_flag = "-k" if service_cfg.get("health_insecure", False) else ""
        try:
            result = subprocess.run(
                f"curl -s -o /dev/null -w '%{{http_code}}' --connect-timeout 5 {insecure_flag} '{health_url}'",
                shell=True, capture_output=True, text=True, timeout=10
            )
            code = int(result.stdout.strip().replace("'", ""))
            return "online" if code < 500 else "offline"
        except Exception:
            return "offline"


def refresh_all_health():
    """Refresh health status for all services."""
    for name, cfg in SERVICE_REGISTRY.items():
        try:
            status = check_health(name, cfg)
            with cache_lock:
                cache["health"][name] = {"status": status, "timestamp": time.time()}
        except Exception as e:
            logger.error(f"Health check failed for {name}: {e}")
            with cache_lock:
                cache["health"][name] = {"status": "unknown", "timestamp": time.time()}


# ============================================================
# Version Detection
# ============================================================

def get_container_version_info(host_ip, container_name):
    """Get current image ref, container image ID, tag image ID, tag RepoDigest,
    and version label from a running container.

    Uses a multi-step approach to handle the case where a tag has been re-pulled
    but the container not yet recreated:
    1. docker inspect (container) → image ref, container image ID, version label
    2. docker image inspect (tag) → tag image ID, RepoDigests

    Returns: (image_ref, container_image_id, tag_image_id, tag_repo_digest, version_label)
    """
    # Step 1: Get image reference, container image ID, and version label
    inspect_fmt = (
        "'docker inspect {cname} --format "
        "\"{{{{.Config.Image}}}}|{{{{.Image}}}}|{{{{index .Config.Labels \\\"org.opencontainers.image.version\\\"}}}}\" "
        "2>/dev/null'"
    ).format(cname=container_name)

    stdout, rc = run_ssh_command(host_ip, inspect_fmt, timeout=15)
    if rc != 0 or not stdout:
        return None, None, None, None, None

    parts = stdout.split("|")
    if len(parts) < 3:
        return None, None, None, None, None

    image_ref = parts[0]            # e.g., ghcr.io/immich-app/immich-server:release
    container_image_id = parts[1]   # e.g., sha256:e6a6298e... (image the container runs)
    version_label = parts[2]        # e.g., v2.4.1 or empty

    # Step 2: Get tag's current image ID and RepoDigests
    tag_cmd = (
        "'docker image inspect {image} --format "
        "\"{{{{.Id}}}}|{{{{index .RepoDigests 0}}}}\" 2>/dev/null'"
    ).format(image=image_ref)

    tag_image_id = None
    tag_repo_digest = None
    tag_stdout, tag_rc = run_ssh_command(host_ip, tag_cmd, timeout=15)
    if tag_rc == 0 and tag_stdout:
        tag_parts = tag_stdout.split("|")
        if len(tag_parts) >= 1:
            tag_image_id = tag_parts[0]      # sha256:... (current tag image ID)
        if len(tag_parts) >= 2 and tag_parts[1]:
            raw = tag_parts[1]
            # Extract sha256:... from repo@sha256:...
            if "@" in raw:
                tag_repo_digest = raw.split("@", 1)[1]
            elif raw.startswith("sha256:"):
                tag_repo_digest = raw

    # Try to extract version from tag if no label
    if not version_label:
        tag_match = re.search(r':([v]?[\d]+\.[\d]+[\.\d]*)', image_ref)
        if tag_match:
            version_label = tag_match.group(1).lstrip('v')

    # If still no version, use short digest
    if not version_label and container_image_id:
        version_label = container_image_id[:19] if container_image_id.startswith("sha256:") else container_image_id[:12]

    return image_ref, container_image_id, tag_image_id, tag_repo_digest, version_label or "unknown"


def get_registry_digest(image_ref):
    """Query Docker Hub or GHCR for the latest manifest digest of an image."""
    if not http_requests:
        return None

    # Check registry cache first
    with cache_lock:
        cached = cache["registry"].get(image_ref)
        if cached and (time.time() - cached["timestamp"]) < REGISTRY_CACHE_TTL:
            return cached["digest"]

    try:
        # Parse image reference: namespace/repo:tag
        ref = image_ref
        tag = "latest"
        if ":" in ref:
            ref, tag = ref.rsplit(":", 1)

        # Determine registry
        if ref.startswith("ghcr.io/"):
            return _get_ghcr_digest(ref, tag, image_ref)
        elif ref.startswith("lscr.io/"):
            # LinuxServer images are on GHCR
            ghcr_ref = ref.replace("lscr.io/", "ghcr.io/")
            return _get_ghcr_digest(ghcr_ref, tag, image_ref)
        else:
            return _get_dockerhub_digest(ref, tag, image_ref)
    except Exception as e:
        logger.warning(f"Registry lookup failed for {image_ref}: {e}")
        return None


def _get_dockerhub_digest(repo, tag, cache_key):
    """Get digest from Docker Hub.

    Requests manifest list/index types first so multi-arch images return the
    manifest list digest (matching what Docker stores in RepoDigests at pull time).
    """
    # Normalize repo name
    if "/" not in repo:
        repo = f"library/{repo}"

    # Get auth token (anonymous)
    token_url = f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull"
    token_resp = http_requests.get(token_url, timeout=10)
    token_resp.raise_for_status()
    token = token_resp.json()["token"]

    # Get manifest digest via HEAD request
    # Include manifest list/index types so multi-arch images return the list digest
    manifest_url = f"https://registry-1.docker.io/v2/{repo}/manifests/{tag}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": ", ".join([
            "application/vnd.oci.image.index.v1+json",
            "application/vnd.docker.distribution.manifest.list.v2+json",
            "application/vnd.docker.distribution.manifest.v2+json",
            "application/vnd.oci.image.manifest.v1+json",
        ])
    }
    resp = http_requests.head(manifest_url, headers=headers, timeout=10)

    # Log rate limit
    remaining = resp.headers.get("RateLimit-Remaining")
    if remaining:
        logger.info(f"Docker Hub rate limit remaining: {remaining}")

    digest = resp.headers.get("Docker-Content-Digest")
    if digest:
        with cache_lock:
            cache["registry"][cache_key] = {"digest": digest, "timestamp": time.time()}
    return digest


def _get_ghcr_digest(repo, tag, cache_key):
    """Get digest from GitHub Container Registry.

    Requests manifest list/index types first so multi-arch images return the
    manifest list digest (matching what Docker stores in RepoDigests at pull time).
    """
    # Remove ghcr.io/ prefix for API
    repo_path = repo.replace("ghcr.io/", "")

    # Get anonymous token
    token_url = f"https://ghcr.io/token?service=ghcr.io&scope=repository:{repo_path}:pull"
    token_resp = http_requests.get(token_url, timeout=10)
    token_resp.raise_for_status()
    token = token_resp.json()["token"]

    # Get manifest digest
    # Include manifest list/index types so multi-arch images return the list digest
    manifest_url = f"https://ghcr.io/v2/{repo_path}/manifests/{tag}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": ", ".join([
            "application/vnd.oci.image.index.v1+json",
            "application/vnd.docker.distribution.manifest.list.v2+json",
            "application/vnd.docker.distribution.manifest.v2+json",
            "application/vnd.oci.image.manifest.v1+json",
        ])
    }
    resp = http_requests.head(manifest_url, headers=headers, timeout=10)
    digest = resp.headers.get("Docker-Content-Digest")
    if digest:
        with cache_lock:
            cache["registry"][cache_key] = {"digest": digest, "timestamp": time.time()}
    return digest


def refresh_all_versions():
    """Refresh version info for all Docker-based services.

    Update detection uses a two-tier approach:
    1. Local check: compare container image ID vs tag image ID (catches pulled-but-not-recreated)
    2. Remote check: compare tag RepoDigest vs registry digest (catches new upstream releases)
    An update is available if EITHER check shows a difference.
    """
    for name, cfg in SERVICE_REGISTRY.items():
        if cfg.get("type") == "http_only":
            continue
        if cfg.get("registry") == "local":
            # Local builds: just get current version, no upstream check
            host_ip = cfg.get("host_ip")
            container = cfg.get("container_name")
            if host_ip and container:
                image_ref, container_image_id, tag_image_id, tag_repo_digest, version = \
                    get_container_version_info(host_ip, container)
                with cache_lock:
                    cache["versions"][name] = {
                        "current": version or "custom",
                        "current_digest": container_image_id or "",
                        "image_ref": image_ref or "",
                        "latest_digest": "",
                        "update_available": False,
                        "timestamp": time.time(),
                    }
            continue

        # Docker-based services: get current + check upstream
        host_ip = cfg.get("host_ip")
        container = cfg.get("container_name")
        if not host_ip or not container:
            continue

        try:
            image_ref, container_image_id, tag_image_id, tag_repo_digest, version = \
                get_container_version_info(host_ip, container)
            if not image_ref:
                with cache_lock:
                    cache["versions"][name] = {
                        "current": "unknown", "current_digest": "",
                        "image_ref": "", "latest_digest": "",
                        "update_available": False, "timestamp": time.time(),
                    }
                continue

            update_available = False

            # Tier 1: Local check — is the container running an older image than
            # the locally-pulled tag? (e.g. Watchtower pulled but didn't recreate)
            if container_image_id and tag_image_id and container_image_id != tag_image_id:
                update_available = True
                logger.info(f"Local update detected for {name}: container={container_image_id[:19]} tag={tag_image_id[:19]}")

            # Tier 2: Remote check — is there a newer image on the registry?
            if not update_available and tag_repo_digest:
                latest_digest = get_registry_digest(image_ref)
                if latest_digest and latest_digest != tag_repo_digest:
                    update_available = True
                    logger.info(f"Remote update detected for {name}: local={tag_repo_digest[:19]} registry={latest_digest[:19]}")

            with cache_lock:
                cache["versions"][name] = {
                    "current": version or "unknown",
                    "current_digest": container_image_id or "",
                    "image_ref": image_ref or "",
                    "latest_digest": tag_repo_digest or "",
                    "update_available": update_available,
                    "timestamp": time.time(),
                }
        except Exception as e:
            logger.error(f"Version check failed for {name}: {e}")
            with cache_lock:
                cache["versions"][name] = {
                    "current": "error", "current_digest": "",
                    "image_ref": "", "latest_digest": "",
                    "update_available": False, "timestamp": time.time(),
                }


# ============================================================
# Update Mechanism
# ============================================================

def perform_update(task_id, service_name, cfg):
    """Execute docker compose pull + up for a service. Runs in background thread."""
    lock = update_locks.setdefault(service_name, threading.Lock())
    with lock:
        host_ip = cfg["host_ip"]
        compose_dir = cfg["compose_dir"]
        container = cfg["container_name"]

        logger.info(f"UPDATE START: {service_name} on {host_ip} in {compose_dir}")
        update_tasks[task_id]["output"] += f"Pulling {container} on {host_ip}...\n"


        # Get the docker-compose service name from container labels (may differ from container name)
        svc_stdout, svc_rc = run_ssh_command(
            host_ip,
            f"'docker inspect {container} --format \"{{{{index .Config.Labels \\\"com.docker.compose.service\\\"}}}}\"'",
            timeout=30
        )
        compose_service = svc_stdout.strip() if svc_rc == 0 and svc_stdout.strip() else container
        logger.info(f"Container {container} has compose service name: {compose_service}")
        update_tasks[task_id]["output"] += f"Compose service: {compose_service}\n"

        # Step 1: Pull new image
        stdout, rc = run_ssh_command(
            host_ip,
            f"'cd {compose_dir} && docker compose pull {compose_service}'",
            timeout=300
        )
        update_tasks[task_id]["output"] += f"Pull output: {stdout}\n"

        if rc != 0:
            update_tasks[task_id]["status"] = "failed"
            update_tasks[task_id]["output"] += f"Pull failed (rc={rc})\n"
            update_tasks[task_id]["completed"] = datetime.now().isoformat()
            logger.error(f"UPDATE FAILED (pull): {service_name} rc={rc}")
            return

        # Step 2: Recreate container
        stdout, rc = run_ssh_command(
            host_ip,
            f"'cd {compose_dir} && docker compose up -d --force-recreate {compose_service}'",
            timeout=180
        )
        update_tasks[task_id]["output"] += f"Recreate output: {stdout}\n"

        if rc == 0:
            update_tasks[task_id]["status"] = "success"
            logger.info(f"UPDATE SUCCESS: {service_name}")
            # Refresh version cache for this service
            try:
                image_ref, image_digest, version = get_container_version_info(host_ip, container)
                with cache_lock:
                    cache["versions"][service_name] = {
                        "current": version or "unknown",
                        "current_digest": image_digest or "",
                        "image_ref": image_ref or "",
                        "latest_digest": image_digest or "",  # Just updated, so current = latest
                        "update_available": False,
                        "timestamp": time.time(),
                    }
            except Exception:
                pass
        else:
            update_tasks[task_id]["status"] = "failed"
            update_tasks[task_id]["output"] += f"Recreate failed (rc={rc})\n"
            logger.error(f"UPDATE FAILED (recreate): {service_name} rc={rc}")

        update_tasks[task_id]["completed"] = datetime.now().isoformat()


# ============================================================
# Background Threads
# ============================================================

def health_refresh_loop():
    """Background thread that refreshes health data."""
    while not stop_event.is_set():
        try:
            refresh_all_health()
        except Exception as e:
            logger.error(f"Health refresh error: {e}")
        stop_event.wait(HEALTH_REFRESH_INTERVAL)


def version_refresh_loop():
    """Background thread that refreshes version data."""
    # Initial delay to let the app start
    stop_event.wait(10)
    while not stop_event.is_set():
        try:
            refresh_all_versions()
        except Exception as e:
            logger.error(f"Version refresh error: {e}")
        stop_event.wait(VERSION_REFRESH_INTERVAL)


def cleanup_old_tasks():
    """Remove update tasks older than 1 hour."""
    while not stop_event.is_set():
        cutoff = time.time() - 3600
        to_remove = [
            tid for tid, task in update_tasks.items()
            if task.get("completed") and
            datetime.fromisoformat(task["completed"]).timestamp() < cutoff
        ]
        for tid in to_remove:
            update_tasks.pop(tid, None)
        stop_event.wait(600)


def start_background_threads():
    """Start all background refresh threads."""
    threads = [
        threading.Thread(target=health_refresh_loop, daemon=True, name="health-refresh"),
        threading.Thread(target=version_refresh_loop, daemon=True, name="version-refresh"),
        threading.Thread(target=cleanup_old_tasks, daemon=True, name="task-cleanup"),
    ]
    for t in threads:
        t.start()
    return threads


# ============================================================
# Helper: Build service response
# ============================================================

def build_service_data(name, cfg):
    """Build the JSON response for a single service."""
    with cache_lock:
        health_data = cache["health"].get(name, {})
        version_data = cache["versions"].get(name, {})

    is_http_only = cfg.get("type") == "http_only"
    is_local = cfg.get("registry") == "local"
    is_blacklisted = name in UPDATE_BLACKLIST

    result = {
        "name": name,
        "display_name": cfg["display_name"],
        "category": cfg["category"],
        "icon": cfg["icon"],
        "health": health_data.get("status", "unknown"),
        "web_url": cfg.get("web_url", ""),
        "host": cfg.get("host_ip", ""),
        "type": "http_only" if is_http_only else ("local" if is_local else "docker"),
        "current_version": version_data.get("current", "N/A" if is_http_only else "..."),
        "update_available": version_data.get("update_available", False),
        "can_update": not is_http_only and not is_local and not is_blacklisted and version_data.get("update_available", False),
        "blacklisted": is_blacklisted,
    }
    return result


# ============================================================
# API Routes
# ============================================================

@app.route('/health')
def health():
    return jsonify({"status": "ok", "services": len(SERVICE_REGISTRY)})


@app.route('/api/services')
def all_services():
    """Return all services grouped by category."""
    grouped = {}
    for cat_key, cat_name in CATEGORIES.items():
        services = []
        for name, cfg in SERVICE_REGISTRY.items():
            if cfg["category"] == cat_key:
                services.append(build_service_data(name, cfg))
        grouped[cat_key] = {
            "category": cat_key,
            "category_display": cat_name,
            "services": services,
            "total": len(services),
            "online": sum(1 for s in services if s["health"] == "online"),
            "updates_available": sum(1 for s in services if s["update_available"]),
        }

    total_services = sum(g["total"] for g in grouped.values())
    total_online = sum(g["online"] for g in grouped.values())
    total_updates = sum(g["updates_available"] for g in grouped.values())

    return jsonify({
        "categories": grouped,
        "summary": {
            "total": total_services,
            "online": total_online,
            "updates_available": total_updates,
            "last_health_check": datetime.now().isoformat(),
        }
    })


@app.route('/api/services/<category>')
def services_by_category(category):
    """Return services for a specific category."""
    if category not in CATEGORIES:
        return jsonify({"error": "Unknown category"}), 404

    services = []
    for name, cfg in SERVICE_REGISTRY.items():
        if cfg["category"] == category:
            services.append(build_service_data(name, cfg))

    return jsonify({
        "category": category,
        "category_display": CATEGORIES[category],
        "services": services,
        "total": len(services),
        "online": sum(1 for s in services if s["health"] == "online"),
        "updates_available": sum(1 for s in services if s["update_available"]),
        "api_key": UPDATE_API_KEY,
    })


@app.route('/api/summary')
def summary():
    """Return a summary of all services for the sidebar widget."""
    total = len(SERVICE_REGISTRY)
    with cache_lock:
        online = sum(1 for h in cache["health"].values() if h.get("status") == "online")
        updates = sum(1 for v in cache["versions"].values() if v.get("update_available"))

    categories_list = []
    for cat_key, cat_name in CATEGORIES.items():
        cat_services = [n for n, c in SERVICE_REGISTRY.items() if c["category"] == cat_key]
        with cache_lock:
            cat_online = sum(1 for n in cat_services if cache["health"].get(n, {}).get("status") == "online")
            cat_updates = sum(1 for n in cat_services if cache["versions"].get(n, {}).get("update_available"))
        categories_list.append({
            "key": cat_key,
            "name": cat_name,
            "total": len(cat_services),
            "online": cat_online,
            "updates": cat_updates,
        })

    return jsonify({
        "total": total,
        "online": online,
        "offline": total - online,
        "updates_available": updates,
        "categories": categories_list,
    })


@app.route('/api/update/<service_name>', methods=['GET', 'POST'])
def trigger_update(service_name):
    """Trigger an update for a specific service."""
    # Auth check
    api_key = request.headers.get('X-API-Key', '') or request.args.get('key', '')
    if api_key != UPDATE_API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    if service_name not in SERVICE_REGISTRY:
        return jsonify({"error": "Unknown service"}), 404

    cfg = SERVICE_REGISTRY[service_name]

    if cfg.get("type") == "http_only":
        return jsonify({"error": "Not a Docker service"}), 400

    if cfg.get("registry") == "local":
        return jsonify({"error": "Custom-built service. Redeploy via Ansible."}), 400

    if service_name in UPDATE_BLACKLIST:
        return jsonify({"error": f"Service '{service_name}' is blacklisted from one-click updates for safety."}), 403

    # Check if already updating
    if service_name in update_locks and update_locks[service_name].locked():
        return jsonify({"error": "Update already in progress"}), 409

    task_id = str(uuid.uuid4())[:8]
    update_tasks[task_id] = {
        "status": "running",
        "service": service_name,
        "started": datetime.now().isoformat(),
        "output": "",
        "completed": None,
    }

    thread = threading.Thread(
        target=perform_update, args=(task_id, service_name, cfg),
        daemon=True, name=f"update-{service_name}"
    )
    thread.start()

    if request.method == 'GET':
        return redirect('https://glance.hrmsmrflrii.xyz/%F0%9F%9B%A0%EF%B8%8F-services')
    return jsonify({"task_id": task_id, "status": "started", "service": service_name})


@app.route('/api/update-status/<task_id>')
def update_status(task_id):
    """Check the status of an update task."""
    task = update_tasks.get(task_id)
    if not task:
        return jsonify({"error": "Unknown task"}), 404
    return jsonify(task)


@app.route('/refresh', methods=['POST', 'GET'])
def force_refresh():
    """Force refresh all caches."""
    threading.Thread(target=refresh_all_health, daemon=True).start()
    threading.Thread(target=refresh_all_versions, daemon=True).start()
    return jsonify({"status": "refresh started"})


# ============================================================
# App Startup
# ============================================================

_threads_started = False

@app.before_request
def ensure_threads():
    global _threads_started
    if not _threads_started:
        _threads_started = True
        start_background_threads()
        logger.info("Background threads started")


def shutdown():
    stop_event.set()


atexit.register(shutdown)

if __name__ == '__main__':
    start_background_threads()
    app.run(host='0.0.0.0', port=5070, debug=False)

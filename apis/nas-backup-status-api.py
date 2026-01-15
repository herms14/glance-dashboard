#!/usr/bin/env python3
"""
NAS Backup Status API - Enhanced with durations and VM names
Reports PBS backups stored on NAS for Glance dashboard
"""

import subprocess
import json
import re
import time
import threading
import atexit
from datetime import datetime, timedelta
from flask import Flask, jsonify

app = Flask(__name__)

# Configuration
PBS_HOST = "192.168.20.50"
SSH_KEY = "/root/.ssh/homelab_ed25519"
LOG_FILE = "/var/log/pbs-nas-backup.log"
LOCK_FILE = "/var/run/pbs-nas-backup.lock"
NAS_BACKUP_DIR = "/mnt/nas-backup/pbs-offsite"
PBS_DAILY_PATH = "/backup-ssd"
PBS_MAIN_PATH = "/backup"

# VM/CT Name mapping (VMID -> Name)
VM_NAMES = {
    "100": "pbs-server",
    "101": "docker-lxc-glance",
    "103": "pihole-lxc",
    "104": "traefik-lxc",
    "105": "authentik-lxc",
    "106": "gitlab-lxc",
    "107": "immich-lxc",
    "108": "karakeep-lxc",
    "109": "uptime-kuma-lxc",
    "110": "lagident-lxc",
    "116": "wizarr-lxc",
    "117": "tracearr-lxc",
    "118": "linkwarden-lxc",
    "119": "hoarder-lxc",
    "120": "homebox-lxc",
    "121": "windows-11-mgmt",
    "200": "ansible-controller",
    "201": "docker-media",
    "202": "docker-utils",
    "203": "linux-syslog",
    "204": "docker-n8n",
    "205": "plex-meta-mgr",
    "206": "frigate-nvr",
    "207": "github-runner",
    "300": "k8s-ctrl-01",
    "301": "k8s-ctrl-02",
    "302": "k8s-ctrl-03",
    "303": "k8s-work-01",
    "304": "k8s-work-02",
    "305": "k8s-work-03",
    "306": "k8s-work-04",
    "307": "k8s-work-05",
    "308": "k8s-work-06",
    "309": "k8s-work-07",
    "310": "k8s-work-08",
    "311": "k8s-work-09",
    "1000": "windows-server",
}

# Cache configuration
CACHE_TTL = 300  # 5 minutes
CACHE_REFRESH_INTERVAL = 240  # 4 minutes
cache = {
    "backups": {"data": None, "timestamp": 0},
    "status": {"data": None, "timestamp": 0}
}
cache_lock = threading.Lock()
background_thread = None
stop_event = threading.Event()

def run_ssh_command(cmd, timeout=30):
    """Run command on PBS via SSH"""
    try:
        result = subprocess.run(
            ["ssh", "-i", SSH_KEY, "-o", "StrictHostKeyChecking=no",
             "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=5",
             f"root@{PBS_HOST}", cmd],
            capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "SSH timeout", 1
    except Exception as e:
        return str(e), 1

def format_duration(seconds):
    """Format seconds into human-readable duration"""
    if seconds is None or seconds < 0:
        return "N/A"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}m {secs}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"

def get_sync_status():
    """Get current backup sync status"""
    lock_check, _ = run_ssh_command(f"test -f {LOCK_FILE} && echo 'running' || echo 'not_running'")
    if lock_check == "running":
        return "running"

    log_check, rc = run_ssh_command(f"tail -10 {LOG_FILE} 2>/dev/null | grep -E '(completed successfully|ERROR|FAILED)'")
    if rc == 0:
        if "completed successfully" in log_check:
            return "success"
        elif "ERROR" in log_check or "FAILED" in log_check:
            return "failed"

    dir_check, rc = run_ssh_command(f"test -d {NAS_BACKUP_DIR} && echo 'exists'")
    if dir_check == "exists":
        return "success"

    return "unknown"

def get_last_sync_info():
    """Get timestamp, sizes, and duration from log file"""
    log_output, rc = run_ssh_command(f"tail -100 {LOG_FILE} 2>/dev/null")

    last_sync = "Never"
    main_size = "N/A"
    daily_size = "N/A"
    duration = "N/A"
    start_time = None
    end_time = None

    if rc == 0 and log_output:
        lines = log_output.split('\n')

        # Find the most recent complete backup session
        for i, line in enumerate(lines):
            if "Starting PBS backup to NAS" in line:
                match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                if match:
                    start_time = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")

            elif "Backup completed successfully" in line:
                match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                if match:
                    end_time = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
                    last_sync = match.group(1)

            elif "Main datastore on NAS:" in line:
                match = re.search(r'Main datastore on NAS:\s*(\S+)', line)
                if match:
                    main_size = match.group(1)

            elif "Daily datastore on NAS:" in line:
                match = re.search(r'Daily datastore on NAS:\s*(\S+)', line)
                if match:
                    daily_size = match.group(1)

        # Calculate duration if we have both times
        if start_time and end_time and end_time > start_time:
            diff = (end_time - start_time).total_seconds()
            duration = format_duration(diff)

    return last_sync, main_size, daily_size, duration

def get_backup_job_status():
    """Get last backup time, status, and duration for each datastore"""
    result = {
        "daily": {"last_backup": "Unknown", "status": "unknown", "count": 0, "duration": "N/A"},
        "main": {"last_backup": "Unknown", "status": "unknown", "count": 0, "duration": "N/A"}
    }

    for datastore, path in [("daily", PBS_DAILY_PATH), ("main", PBS_MAIN_PATH)]:
        # Get latest backup
        cmd = f"find {path} -maxdepth 4 -type d -name '20*T*' 2>/dev/null | sort -r | head -1"
        output, rc = run_ssh_command(cmd)
        if rc == 0 and output:
            match = re.search(r'(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})', output)
            if match:
                result[datastore]["last_backup"] = f"{match.group(1)} {match.group(2)}"
                result[datastore]["status"] = "success"

        # Get backup count
        count_cmd = f"find {path} -maxdepth 4 -type d -name '20*T*' 2>/dev/null | wc -l"
        count_out, rc = run_ssh_command(count_cmd)
        if rc == 0 and count_out.isdigit():
            result[datastore]["count"] = int(count_out)

        # Get backup job duration (time from first to last backup on most recent backup day)
        recent_cmd = f"find {path} -maxdepth 4 -type d -name '20*T*' 2>/dev/null | sort -r | head -50"
        recent_out, rc = run_ssh_command(recent_cmd)
        if rc == 0 and recent_out:
            timestamps = []
            backup_day = None
            for line in recent_out.split('\n'):
                match = re.search(r'(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):(\d{2})', line)
                if match:
                    day = match.group(1)
                    if backup_day is None:
                        backup_day = day
                    if day == backup_day:
                        ts = datetime.strptime(f"{day} {match.group(2)}:{match.group(3)}:{match.group(4)}", "%Y-%m-%d %H:%M:%S")
                        timestamps.append(ts)

            if len(timestamps) >= 2:
                duration = (max(timestamps) - min(timestamps)).total_seconds()
                result[datastore]["duration"] = format_duration(duration)

        # Check if backups are recent (stale check)
        try:
            now = datetime.now()
            if result[datastore]["last_backup"] != "Unknown":
                backup_time = datetime.strptime(result[datastore]["last_backup"], "%Y-%m-%d %H:%M")
                if datastore == "daily" and (now - backup_time) > timedelta(hours=26):
                    result[datastore]["status"] = "stale"
                elif datastore == "main" and (now - backup_time) > timedelta(days=8):
                    result[datastore]["status"] = "stale"
        except:
            pass

    return result

def fetch_nas_backups():
    """Fetch list of backups stored on NAS with VM names"""
    backups = []

    for datastore in ["main", "daily"]:
        for btype in ["vm", "ct"]:
            cmd = f"ls -1 {NAS_BACKUP_DIR}/{datastore}/{btype}/ 2>/dev/null"
            output, rc = run_ssh_command(cmd)

            if rc == 0 and output:
                for vmid in output.strip().split('\n'):
                    if vmid and vmid.isdigit():
                        snap_cmd = f"ls -1 {NAS_BACKUP_DIR}/{datastore}/{btype}/{vmid}/ 2>/dev/null | grep -E '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}T' | sort -r | head -1"
                        snap_output, snap_rc = run_ssh_command(snap_cmd)

                        if snap_rc == 0 and snap_output:
                            last_backup = "Unknown"
                            match = re.match(r'(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})', snap_output)
                            if match:
                                last_backup = f"{match.group(1)} {match.group(2)}"

                            # Get VM name from lookup table
                            vm_name = VM_NAMES.get(vmid, f"{btype.upper()}-{vmid}")

                            backups.append({
                                "vmid": vmid,
                                "name": vm_name,
                                "type": btype.upper(),
                                "datastore": datastore,
                                "last_backup": last_backup
                            })

    backups.sort(key=lambda x: int(x["vmid"]))

    # Deduplicate - prefer main datastore
    seen = {}
    for b in backups:
        key = b["vmid"]
        if key not in seen or b["datastore"] == "main":
            seen[key] = b

    return list(seen.values())

def fetch_status():
    """Fetch sync status with durations"""
    sync_status = get_sync_status()
    last_sync, main_size, daily_size, nas_duration = get_last_sync_info()
    job_status = get_backup_job_status()

    return {
        "status": sync_status,
        "last_sync": last_sync,
        "main_size": main_size,
        "daily_size": daily_size,
        "nas_sync_duration": nas_duration,
        "nas_target": "192.168.20.31:/volume2/ProxmoxData/pbs-offsite",
        "schedule": "Daily at 2:00 AM",
        "job_status": job_status
    }

def refresh_cache():
    """Refresh all cache data"""
    print(f"[{datetime.now()}] Refreshing cache...")

    try:
        status_data = fetch_status()
        with cache_lock:
            cache["status"]["data"] = status_data
            cache["status"]["timestamp"] = time.time()
        print(f"[{datetime.now()}] Status cache refreshed")
    except Exception as e:
        print(f"[{datetime.now()}] Error refreshing status cache: {e}")

    try:
        backups_data = fetch_nas_backups()
        with cache_lock:
            cache["backups"]["data"] = backups_data
            cache["backups"]["timestamp"] = time.time()
        print(f"[{datetime.now()}] Backups cache refreshed ({len(backups_data)} items)")
    except Exception as e:
        print(f"[{datetime.now()}] Error refreshing backups cache: {e}")

def background_cache_refresh():
    """Background thread to keep cache warm"""
    print(f"[{datetime.now()}] Starting background cache refresh thread")
    refresh_cache()

    while not stop_event.is_set():
        if stop_event.wait(timeout=CACHE_REFRESH_INTERVAL):
            break
        refresh_cache()

    print(f"[{datetime.now()}] Background cache refresh thread stopped")

def start_background_refresh():
    global background_thread
    if background_thread is None or not background_thread.is_alive():
        stop_event.clear()
        background_thread = threading.Thread(target=background_cache_refresh, daemon=True)
        background_thread.start()

def stop_background_refresh():
    stop_event.set()
    if background_thread and background_thread.is_alive():
        background_thread.join(timeout=5)

atexit.register(stop_background_refresh)

def get_cached(key):
    with cache_lock:
        if cache[key]["data"] is not None:
            return cache[key]["data"]
    return None

@app.route('/status')
def status():
    try:
        data = get_cached("status")
        if data is None:
            data = fetch_status()
            with cache_lock:
                cache["status"]["data"] = data
                cache["status"]["timestamp"] = time.time()
        return jsonify(data)
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/backups')
def backups():
    try:
        backup_list = get_cached("backups")
        if backup_list is None:
            backup_list = fetch_nas_backups()
            with cache_lock:
                cache["backups"]["data"] = backup_list
                cache["backups"]["timestamp"] = time.time()
        return jsonify({
            "backups": backup_list,
            "total_count": len(backup_list),
            "vm_count": len([b for b in backup_list if b["type"] == "VM"]),
            "ct_count": len([b for b in backup_list if b["type"] == "CT"]),
            "cached": True
        })
    except Exception as e:
        return jsonify({"backups": [], "error": str(e)}), 500

@app.route('/job-status')
def job_status():
    try:
        data = get_cached("status")
        if data:
            return jsonify(data.get("job_status", {}))
        return jsonify({"error": "Cache not ready"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/refresh')
def refresh():
    refresh_cache()
    return jsonify({"status": "cache refreshed"})

@app.route('/health')
def health():
    cache_status = {
        "status_cached": cache["status"]["data"] is not None,
        "backups_cached": cache["backups"]["data"] is not None
    }
    return jsonify({
        "status": "healthy",
        "service": "nas-backup-status-api",
        "cache": cache_status
    })

start_background_refresh()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9102)

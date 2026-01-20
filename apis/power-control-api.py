#!/usr/bin/env python3
"""
Power Control API for Glance Dashboard
Provides endpoints for Wake-on-LAN, shutdown, and backup triggering.
Includes embedded web UI for Glance iframe integration.
Runs on docker-vm-core-utilities01 (192.168.40.13) port 5057
"""

import os
import subprocess
import threading
import time
from datetime import datetime
from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS
import paramiko

app = Flask(__name__)
CORS(app)

# Configuration
PROXMOX_NODES = {
    "node01": {"ip": "192.168.20.20", "mac": "38:05:25:32:82:76"},
    "node02": {"ip": "192.168.20.21", "mac": "84:47:09:4d:7a:ca"},
    "node03": {"ip": "192.168.20.22", "mac": "d8:43:ae:a8:4c:a7"},
}

PBS_HOST = "192.168.20.50"
PBS_USER = "root"
SSH_KEY_PATH = os.getenv("SSH_KEY_PATH", "/app/keys/homelab_ed25519")

# Operation status tracking
operation_status = {
    "wol": {"status": "idle", "message": "", "timestamp": None},
    "shutdown": {"status": "idle", "message": "", "timestamp": None},
    "backup": {"status": "idle", "message": "", "timestamp": None},
}

# Embedded HTML UI for Glance iframe
CONTROL_PANEL_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Inter', sans-serif;
            background: transparent;
            color: #e4e4e7;
            padding: 16px 20px;
        }

        .container {
            display: flex;
            align-items: center;
            gap: 20px;
        }

        .nodes {
            display: flex;
            gap: 8px;
        }

        .node {
            display: flex;
            align-items: center;
            gap: 6px;
            padding: 6px 10px;
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 6px;
        }

        .node-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            transition: all 0.3s ease;
        }

        .node-dot.online {
            background: #10b981;
            box-shadow: 0 0 8px rgba(16, 185, 129, 0.5);
        }
        .node-dot.offline {
            background: #ef4444;
            box-shadow: 0 0 8px rgba(239, 68, 68, 0.5);
        }
        .node-dot.unknown {
            background: #3f3f46;
        }

        .node-label {
            font-size: 11px;
            font-weight: 500;
            color: #71717a;
            letter-spacing: 0.3px;
        }

        .divider {
            width: 1px;
            height: 32px;
            background: rgba(255,255,255,0.08);
        }

        .actions {
            display: flex;
            gap: 8px;
            flex: 1;
            justify-content: flex-end;
        }

        .action-btn {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 10px 16px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 12px;
            font-weight: 500;
            letter-spacing: 0.2px;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.08);
            color: #a1a1aa;
        }

        .action-btn:hover {
            background: rgba(255,255,255,0.08);
            border-color: rgba(255,255,255,0.15);
            color: #e4e4e7;
            transform: translateY(-1px);
        }

        .action-btn:active {
            transform: translateY(0);
        }

        .action-btn:disabled {
            opacity: 0.4;
            cursor: not-allowed;
            transform: none;
        }

        .action-btn.wake:hover {
            background: rgba(16, 185, 129, 0.1);
            border-color: rgba(16, 185, 129, 0.3);
            color: #10b981;
        }

        .action-btn.shutdown:hover {
            background: rgba(239, 68, 68, 0.1);
            border-color: rgba(239, 68, 68, 0.3);
            color: #ef4444;
        }

        .action-btn.backup:hover {
            background: rgba(59, 130, 246, 0.1);
            border-color: rgba(59, 130, 246, 0.3);
            color: #3b82f6;
        }

        .action-btn svg {
            width: 14px;
            height: 14px;
            opacity: 0.7;
        }

        .action-btn:hover svg {
            opacity: 1;
        }

        .status-text {
            font-size: 10px;
            color: #52525b;
            margin-left: 2px;
        }

        .spinner {
            width: 12px;
            height: 12px;
            border: 1.5px solid rgba(255,255,255,0.2);
            border-top-color: currentColor;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        /* Modal */
        .modal-overlay {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.7);
            backdrop-filter: blur(4px);
            justify-content: center;
            align-items: center;
            z-index: 1000;
        }

        .modal-overlay.active {
            display: flex;
        }

        .modal {
            background: #18181b;
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 24px;
            max-width: 320px;
            text-align: center;
            box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5);
        }

        .modal-icon {
            width: 48px;
            height: 48px;
            margin: 0 auto 16px;
            background: rgba(239, 68, 68, 0.1);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .modal-icon svg {
            width: 24px;
            height: 24px;
            color: #ef4444;
        }

        .modal h3 {
            font-size: 16px;
            font-weight: 600;
            color: #fafafa;
            margin-bottom: 8px;
        }

        .modal p {
            font-size: 13px;
            color: #71717a;
            line-height: 1.5;
            margin-bottom: 24px;
        }

        .modal-actions {
            display: flex;
            gap: 12px;
        }

        .modal-btn {
            flex: 1;
            padding: 10px 16px;
            border: none;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.15s ease;
        }

        .modal-btn.cancel {
            background: rgba(255,255,255,0.05);
            color: #a1a1aa;
            border: 1px solid rgba(255,255,255,0.1);
        }

        .modal-btn.cancel:hover {
            background: rgba(255,255,255,0.1);
        }

        .modal-btn.danger {
            background: #ef4444;
            color: white;
        }

        .modal-btn.danger:hover {
            background: #dc2626;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="nodes">
            <div class="node">
                <span class="node-dot unknown" id="node01Dot"></span>
                <span class="node-label">N1</span>
            </div>
            <div class="node">
                <span class="node-dot unknown" id="node02Dot"></span>
                <span class="node-label">N2</span>
            </div>
            <div class="node">
                <span class="node-dot unknown" id="node03Dot"></span>
                <span class="node-label">N3</span>
            </div>
        </div>

        <div class="divider"></div>

        <div class="actions">
            <button class="action-btn wake" id="wolBtn" onclick="sendWol()">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
                </svg>
                <span>Wake</span>
                <span class="status-text" id="wolStatus"></span>
            </button>

            <button class="action-btn shutdown" id="shutdownBtn" onclick="confirmShutdown()">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M18.36 6.64a9 9 0 1 1-12.73 0"/>
                    <line x1="12" y1="2" x2="12" y2="12"/>
                </svg>
                <span>Shutdown</span>
                <span class="status-text" id="shutdownStatus"></span>
            </button>

            <button class="action-btn backup" id="backupBtn" onclick="triggerBackup()">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                    <polyline points="17 8 12 3 7 8"/>
                    <line x1="12" y1="3" x2="12" y2="15"/>
                </svg>
                <span>Backup</span>
                <span class="status-text" id="backupStatus"></span>
            </button>
        </div>
    </div>

    <div class="modal-overlay" id="shutdownModal">
        <div class="modal">
            <div class="modal-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M18.36 6.64a9 9 0 1 1-12.73 0"/>
                    <line x1="12" y1="2" x2="12" y2="12"/>
                </svg>
            </div>
            <h3>Shutdown Cluster</h3>
            <p>All VMs and containers will be stopped gracefully before shutting down the nodes.</p>
            <div class="modal-actions">
                <button class="modal-btn cancel" onclick="closeModal()">Cancel</button>
                <button class="modal-btn danger" onclick="sendShutdown()">Shutdown</button>
            </div>
        </div>
    </div>

    <script>
        const API_BASE = '';

        async function updateNodeStatus() {
            try {
                const resp = await fetch(API_BASE + '/status');
                const data = await resp.json();
                for (const [node, info] of Object.entries(data.nodes)) {
                    const dot = document.getElementById(node + 'Dot');
                    if (dot) dot.className = 'node-dot ' + (info.online ? 'online' : 'offline');
                }
            } catch (e) {
                console.error('Status fetch failed:', e);
            }
        }

        function setLoading(btnId, statusId, loading) {
            const btn = document.getElementById(btnId);
            const status = document.getElementById(statusId);
            btn.disabled = loading;
            status.innerHTML = loading ? '<span class="spinner"></span>' : '';
        }

        async function sendWol() {
            setLoading('wolBtn', 'wolStatus', true);
            try {
                const resp = await fetch(API_BASE + '/wol', { method: 'POST' });
                const data = await resp.json();
                document.getElementById('wolStatus').textContent = data.success ? 'sent' : 'failed';
                pollOperation('wol', 'wolStatus');
            } catch (e) {
                document.getElementById('wolStatus').textContent = 'error';
                document.getElementById('wolBtn').disabled = false;
            }
        }

        function confirmShutdown() {
            document.getElementById('shutdownModal').classList.add('active');
        }

        function closeModal() {
            document.getElementById('shutdownModal').classList.remove('active');
        }

        async function sendShutdown() {
            closeModal();
            setLoading('shutdownBtn', 'shutdownStatus', true);
            try {
                const resp = await fetch(API_BASE + '/shutdown?confirm=true', { method: 'POST' });
                const data = await resp.json();
                document.getElementById('shutdownStatus').textContent = data.success ? 'done' : 'failed';
                pollOperation('shutdown', 'shutdownStatus');
            } catch (e) {
                document.getElementById('shutdownStatus').textContent = 'error';
                document.getElementById('shutdownBtn').disabled = false;
            }
        }

        async function triggerBackup() {
            setLoading('backupBtn', 'backupStatus', true);
            try {
                const resp = await fetch(API_BASE + '/backup', { method: 'POST' });
                const data = await resp.json();
                document.getElementById('backupStatus').textContent = data.success ? 'started' : 'failed';
                pollOperation('backup', 'backupStatus');
            } catch (e) {
                document.getElementById('backupStatus').textContent = 'error';
                document.getElementById('backupBtn').disabled = false;
            }
        }

        async function pollOperation(opType, statusId) {
            const check = async () => {
                try {
                    const resp = await fetch(API_BASE + '/operation/' + opType);
                    const data = await resp.json();
                    if (data.status === 'completed') {
                        document.getElementById(statusId).textContent = '';
                        document.getElementById(opType + 'Btn').disabled = false;
                        updateNodeStatus();
                    } else if (data.status === 'error') {
                        document.getElementById(statusId).textContent = 'error';
                        document.getElementById(opType + 'Btn').disabled = false;
                    } else {
                        setTimeout(check, 3000);
                    }
                } catch (e) {
                    document.getElementById(statusId).textContent = 'error';
                    document.getElementById(opType + 'Btn').disabled = false;
                }
            };
            setTimeout(check, 2000);
        }

        updateNodeStatus();
        setInterval(updateNodeStatus, 30000);
    </script>
</body>
</html>
"""


def get_ssh_client(host, user="root"):
    """Create SSH client connection."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            host,
            username=user,
            key_filename=SSH_KEY_PATH,
            timeout=10
        )
        return client
    except Exception as e:
        print(f"SSH connection failed to {host}: {e}")
        return None


def check_node_online(ip):
    """Check if a node is online via ping."""
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "2", ip],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except:
        return False


def send_wol_packet(mac_address, from_node_ip=None):
    """Send Wake-on-LAN magic packet via SSH from a node on the same VLAN."""
    # WoL packets don't cross VLANs, so we need to send from a node on VLAN 20
    # Try to find an online node to send from
    if from_node_ip is None:
        for node, info in PROXMOX_NODES.items():
            if check_node_online(info["ip"]):
                from_node_ip = info["ip"]
                break

    if from_node_ip is None:
        print(f"No online node found to send WoL from")
        return False

    try:
        client = get_ssh_client(from_node_ip)
        if client:
            # Send WoL from the Proxmox node (same VLAN 20)
            stdin, stdout, stderr = client.exec_command(f"wakeonlan {mac_address} 2>/dev/null || echo 'WoL not installed'")
            output = stdout.read().decode()
            client.close()
            return "magic packet" in output.lower() or "WoL not installed" not in output
        return False
    except Exception as e:
        print(f"WoL via SSH failed for {mac_address}: {e}")
        return False


def wol_all_nodes_async():
    """Wake all nodes asynchronously."""
    global operation_status
    operation_status["wol"] = {
        "status": "running",
        "message": "Sending Wake-on-LAN packets...",
        "timestamp": datetime.now().isoformat()
    }

    results = {}
    for node, info in PROXMOX_NODES.items():
        success = send_wol_packet(info["mac"])
        results[node] = "WoL sent" if success else "Failed"
        time.sleep(0.5)  # Small delay between packets

    # Wait and check if nodes come online
    time.sleep(30)
    online_count = 0
    for node, info in PROXMOX_NODES.items():
        if check_node_online(info["ip"]):
            results[node] = "Online"
            online_count += 1

    operation_status["wol"] = {
        "status": "completed",
        "message": f"{online_count}/3 nodes online",
        "results": results,
        "timestamp": datetime.now().isoformat()
    }


def shutdown_all_nodes_async():
    """Shutdown all nodes asynchronously (reverse order: node03 -> node02 -> node01)."""
    global operation_status
    operation_status["shutdown"] = {
        "status": "running",
        "message": "Initiating shutdown sequence...",
        "timestamp": datetime.now().isoformat()
    }

    results = {}
    shutdown_order = ["node03", "node02", "node01"]

    for node in shutdown_order:
        info = PROXMOX_NODES[node]
        try:
            client = get_ssh_client(info["ip"])
            if client:
                # First stop all VMs and containers on this node
                stdin, stdout, stderr = client.exec_command(
                    "pvesh get /nodes/$(hostname)/qemu --output-format json 2>/dev/null | "
                    "jq -r '.[] | select(.status==\"running\") | .vmid' | "
                    "xargs -I {} qm shutdown {} --timeout 120 2>/dev/null || true"
                )
                stdout.read()

                # Stop containers
                stdin, stdout, stderr = client.exec_command(
                    "pvesh get /nodes/$(hostname)/lxc --output-format json 2>/dev/null | "
                    "jq -r '.[] | select(.status==\"running\") | .vmid' | "
                    "xargs -I {} pct shutdown {} --timeout 60 2>/dev/null || true"
                )
                stdout.read()

                # Wait a bit for graceful shutdown
                time.sleep(10)

                # Initiate node shutdown
                stdin, stdout, stderr = client.exec_command("shutdown -h +1 'Shutdown initiated from Glance Dashboard'")
                stdout.read()
                client.close()
                results[node] = "Shutdown initiated"
            else:
                results[node] = "SSH failed"
        except Exception as e:
            results[node] = f"Error: {str(e)}"

        time.sleep(5)  # Wait between nodes

    operation_status["shutdown"] = {
        "status": "completed",
        "message": "Shutdown sequence completed",
        "results": results,
        "timestamp": datetime.now().isoformat()
    }


def trigger_backup_async():
    """Trigger daily backup job on PBS."""
    global operation_status
    operation_status["backup"] = {
        "status": "running",
        "message": "Triggering backup job...",
        "timestamp": datetime.now().isoformat()
    }

    try:
        # Connect to node01 (primary) to trigger backup
        client = get_ssh_client(PROXMOX_NODES["node01"]["ip"])
        if client:
            # Get the backup job ID for daily backups and run it
            # First, list backup jobs to find the daily one
            stdin, stdout, stderr = client.exec_command(
                "pvesh get /cluster/backup --output-format json"
            )
            output = stdout.read().decode()

            # Trigger vzdump for all VMs/CTs to pbs-daily datastore
            cmd = (
                "vzdump --all 1 --mode snapshot --compress zstd --storage pbs-daily "
                "--mailto root --mailnotification failure --quiet 1 &"
            )
            stdin, stdout, stderr = client.exec_command(cmd)
            # Don't wait for completion - let it run in background
            client.close()

            operation_status["backup"] = {
                "status": "completed",
                "message": "Backup job started",
                "timestamp": datetime.now().isoformat()
            }
        else:
            operation_status["backup"] = {
                "status": "error",
                "message": "SSH connection failed",
                "timestamp": datetime.now().isoformat()
            }
    except Exception as e:
        operation_status["backup"] = {
            "status": "error",
            "message": f"Error: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }


@app.route("/")
def index():
    """Serve the control panel UI."""
    return render_template_string(CONTROL_PANEL_HTML)


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "ok",
        "service": "power-control-api",
        "version": "1.0.0"
    })


@app.route("/status")
def status():
    """Get current status of all nodes and operations."""
    nodes_status = {}
    for node, info in PROXMOX_NODES.items():
        nodes_status[node] = {
            "ip": info["ip"],
            "online": check_node_online(info["ip"])
        }

    return jsonify({
        "nodes": nodes_status,
        "operations": operation_status,
        "timestamp": datetime.now().isoformat()
    })


@app.route("/wol", methods=["POST"])
def wake_on_lan():
    """Wake all Proxmox nodes via Wake-on-LAN."""
    if operation_status["wol"]["status"] == "running":
        return jsonify({
            "success": False,
            "message": "WoL operation already in progress"
        }), 409

    # Start async operation
    thread = threading.Thread(target=wol_all_nodes_async)
    thread.start()

    return jsonify({
        "success": True,
        "message": "Wake-on-LAN initiated for all nodes",
        "nodes": list(PROXMOX_NODES.keys())
    })


@app.route("/shutdown", methods=["POST"])
def shutdown_all():
    """Shutdown all Proxmox nodes gracefully."""
    # Require confirmation parameter for safety
    confirm = request.args.get("confirm", "false").lower() == "true"
    if not confirm:
        return jsonify({
            "success": False,
            "message": "Shutdown requires confirmation. Add ?confirm=true to proceed."
        }), 400

    if operation_status["shutdown"]["status"] == "running":
        return jsonify({
            "success": False,
            "message": "Shutdown operation already in progress"
        }), 409

    # Start async operation
    thread = threading.Thread(target=shutdown_all_nodes_async)
    thread.start()

    return jsonify({
        "success": True,
        "message": "Shutdown sequence initiated",
        "order": ["node03", "node02", "node01"]
    })


@app.route("/backup", methods=["POST"])
def trigger_backup():
    """Trigger daily backup job immediately."""
    if operation_status["backup"]["status"] == "running":
        return jsonify({
            "success": False,
            "message": "Backup operation already in progress"
        }), 409

    # Start async operation
    thread = threading.Thread(target=trigger_backup_async)
    thread.start()

    return jsonify({
        "success": True,
        "message": "Backup job triggered"
    })


@app.route("/operation/<op_type>")
def get_operation_status(op_type):
    """Get status of a specific operation."""
    if op_type not in operation_status:
        return jsonify({"error": "Unknown operation type"}), 404

    return jsonify(operation_status[op_type])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5057, debug=False)

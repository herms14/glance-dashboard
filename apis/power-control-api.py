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
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: transparent;
            color: #fff;
            padding: 12px;
        }
        .control-panel {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
        }
        .control-btn {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 16px 12px;
            border: none;
            border-radius: 12px;
            cursor: pointer;
            transition: all 0.2s ease;
            min-height: 100px;
        }
        .control-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }
        .control-btn:active {
            transform: translateY(0);
        }
        .control-btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        .control-btn .icon {
            font-size: 28px;
            margin-bottom: 8px;
        }
        .control-btn .label {
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .control-btn .status {
            font-size: 10px;
            margin-top: 4px;
            opacity: 0.8;
        }
        .btn-wol {
            background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
            color: white;
        }
        .btn-shutdown {
            background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
            color: white;
        }
        .btn-backup {
            background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
            color: white;
        }
        .node-status {
            display: flex;
            justify-content: center;
            gap: 16px;
            margin-top: 12px;
            padding: 10px;
            background: rgba(255,255,255,0.05);
            border-radius: 8px;
        }
        .node {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 11px;
        }
        .node-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
        }
        .node-dot.online { background: #22c55e; }
        .node-dot.offline { background: #ef4444; }
        .node-dot.unknown { background: #6b7280; }
        .spinner {
            display: inline-block;
            width: 14px;
            height: 14px;
            border: 2px solid rgba(255,255,255,0.3);
            border-top-color: white;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        .confirm-modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.8);
            justify-content: center;
            align-items: center;
            z-index: 1000;
        }
        .confirm-modal.active {
            display: flex;
        }
        .confirm-box {
            background: #1e1e2e;
            padding: 24px;
            border-radius: 12px;
            text-align: center;
            max-width: 300px;
        }
        .confirm-box h3 {
            margin-bottom: 12px;
            color: #ef4444;
        }
        .confirm-box p {
            margin-bottom: 20px;
            color: #888;
            font-size: 13px;
        }
        .confirm-btns {
            display: flex;
            gap: 12px;
            justify-content: center;
        }
        .confirm-btns button {
            padding: 10px 24px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
        }
        .confirm-btns .cancel {
            background: #374151;
            color: #fff;
        }
        .confirm-btns .confirm {
            background: #ef4444;
            color: #fff;
        }
    </style>
</head>
<body>
    <div class="control-panel">
        <button class="control-btn btn-wol" id="wolBtn" onclick="sendWol()">
            <span class="icon">⚡</span>
            <span class="label">Wake All</span>
            <span class="status" id="wolStatus">Ready</span>
        </button>
        <button class="control-btn btn-shutdown" id="shutdownBtn" onclick="confirmShutdown()">
            <span class="icon">🔴</span>
            <span class="label">Shutdown</span>
            <span class="status" id="shutdownStatus">Ready</span>
        </button>
        <button class="control-btn btn-backup" id="backupBtn" onclick="triggerBackup()">
            <span class="icon">📦</span>
            <span class="label">Backup Now</span>
            <span class="status" id="backupStatus">Ready</span>
        </button>
    </div>

    <div class="node-status" id="nodeStatus">
        <div class="node">
            <span class="node-dot unknown" id="node01Dot"></span>
            <span>node01</span>
        </div>
        <div class="node">
            <span class="node-dot unknown" id="node02Dot"></span>
            <span>node02</span>
        </div>
        <div class="node">
            <span class="node-dot unknown" id="node03Dot"></span>
            <span>node03</span>
        </div>
    </div>

    <div class="confirm-modal" id="shutdownModal">
        <div class="confirm-box">
            <h3>⚠️ Confirm Shutdown</h3>
            <p>This will shutdown ALL Proxmox nodes. VMs and containers will be stopped gracefully.</p>
            <div class="confirm-btns">
                <button class="cancel" onclick="closeModal()">Cancel</button>
                <button class="confirm" onclick="sendShutdown()">Shutdown</button>
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
                    if (dot) {
                        dot.className = 'node-dot ' + (info.online ? 'online' : 'offline');
                    }
                }
            } catch (e) {
                console.error('Failed to fetch status:', e);
            }
        }

        function setButtonLoading(btnId, statusId, loading) {
            const btn = document.getElementById(btnId);
            const status = document.getElementById(statusId);
            btn.disabled = loading;
            if (loading) {
                status.innerHTML = '<span class="spinner"></span>';
            }
        }

        async function sendWol() {
            setButtonLoading('wolBtn', 'wolStatus', true);
            try {
                const resp = await fetch(API_BASE + '/wol', { method: 'POST' });
                const data = await resp.json();
                document.getElementById('wolStatus').textContent = data.success ? 'Sent!' : 'Failed';

                // Poll for completion
                pollOperation('wol', 'wolStatus');
            } catch (e) {
                document.getElementById('wolStatus').textContent = 'Error';
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
            setButtonLoading('shutdownBtn', 'shutdownStatus', true);
            try {
                const resp = await fetch(API_BASE + '/shutdown?confirm=true', { method: 'POST' });
                const data = await resp.json();
                document.getElementById('shutdownStatus').textContent = data.success ? 'Initiated' : 'Failed';

                pollOperation('shutdown', 'shutdownStatus');
            } catch (e) {
                document.getElementById('shutdownStatus').textContent = 'Error';
                document.getElementById('shutdownBtn').disabled = false;
            }
        }

        async function triggerBackup() {
            setButtonLoading('backupBtn', 'backupStatus', true);
            try {
                const resp = await fetch(API_BASE + '/backup', { method: 'POST' });
                const data = await resp.json();
                document.getElementById('backupStatus').textContent = data.success ? 'Started!' : 'Failed';

                pollOperation('backup', 'backupStatus');
            } catch (e) {
                document.getElementById('backupStatus').textContent = 'Error';
                document.getElementById('backupBtn').disabled = false;
            }
        }

        async function pollOperation(opType, statusId) {
            const checkStatus = async () => {
                try {
                    const resp = await fetch(API_BASE + '/operation/' + opType);
                    const data = await resp.json();

                    if (data.status === 'completed') {
                        document.getElementById(statusId).textContent = data.message || 'Done';
                        document.getElementById(opType + 'Btn').disabled = false;
                        updateNodeStatus();
                        return;
                    } else if (data.status === 'error') {
                        document.getElementById(statusId).textContent = 'Error';
                        document.getElementById(opType + 'Btn').disabled = false;
                        return;
                    }

                    // Still running, check again
                    setTimeout(checkStatus, 3000);
                } catch (e) {
                    document.getElementById(statusId).textContent = 'Error';
                    document.getElementById(opType + 'Btn').disabled = false;
                }
            };

            setTimeout(checkStatus, 2000);
        }

        // Initial load
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

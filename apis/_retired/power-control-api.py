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

# Embedded HTML UI for Glance iframe - Compact sidebar layout
CONTROL_PANEL_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        html, body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', sans-serif;
            background: rgb(15, 15, 20) !important;
            color: #a1a1aa;
            overflow: hidden;
        }

        .wrapper { padding: 8px; }

        .control-panel { display: flex; flex-direction: column; gap: 8px; }
        .control-panel.hidden { display: none; }

        /* Compact node rows */
        .nodes { display: flex; flex-direction: column; gap: 4px; }

        .node {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 10px;
            background: rgba(255,255,255,0.02);
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.15s ease;
        }

        .node:hover { background: rgba(255,255,255,0.05); }
        .node.selected { background: rgba(139, 92, 246, 0.12); }

        .node-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            flex-shrink: 0;
        }
        .node-dot.online { background: #22c55e; box-shadow: 0 0 6px rgba(34, 197, 94, 0.6); }
        .node-dot.offline { background: #ef4444; box-shadow: 0 0 6px rgba(239, 68, 68, 0.6); }
        .node-dot.unknown { background: #52525b; }

        .node-name {
            flex: 1;
            font-size: 12px;
            font-weight: 500;
            color: #d4d4d8;
        }
        .node.selected .node-name { color: #c4b5fd; }

        .node-ip {
            font-size: 10px;
            color: #52525b;
            font-family: 'SF Mono', Monaco, monospace;
        }

        .node-check {
            width: 14px;
            height: 14px;
            color: #a78bfa;
            opacity: 0;
        }
        .node.selected .node-check { opacity: 1; }

        /* Horizontal action buttons */
        .actions {
            display: flex;
            gap: 6px;
            margin-top: 4px;
        }

        .btn {
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 4px;
            padding: 8px 6px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 10px;
            font-weight: 500;
            transition: all 0.15s ease;
            background: rgba(255,255,255,0.03);
            color: #71717a;
        }

        .btn:hover:not(:disabled) { background: rgba(255,255,255,0.06); }
        .btn:disabled { opacity: 0.3; cursor: not-allowed; }
        .btn svg { width: 14px; height: 14px; }

        .btn.wake { color: #4ade80; }
        .btn.wake:hover:not(:disabled) { background: rgba(34, 197, 94, 0.1); }

        .btn.shutdown { color: #f87171; }
        .btn.shutdown:hover:not(:disabled) { background: rgba(239, 68, 68, 0.1); }

        .btn.backup { color: #60a5fa; }
        .btn.backup:hover:not(:disabled) { background: rgba(96, 165, 250, 0.1); }

        .spinner {
            width: 12px;
            height: 12px;
            border: 1.5px solid rgba(255,255,255,0.1);
            border-top-color: currentColor;
            border-radius: 50%;
            animation: spin 0.6s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        /* Confirmation panel */
        .confirm-panel {
            display: none;
            flex-direction: column;
            gap: 10px;
            padding: 12px;
            background: rgba(239, 68, 68, 0.06);
            border-radius: 6px;
        }
        .confirm-panel.active { display: flex; }

        .confirm-title {
            font-size: 12px;
            font-weight: 600;
            color: #f87171;
            text-align: center;
        }

        .confirm-nodes {
            display: flex;
            flex-wrap: wrap;
            gap: 4px;
            justify-content: center;
        }

        .confirm-node {
            font-size: 10px;
            color: #fca5a5;
            background: rgba(239, 68, 68, 0.1);
            padding: 3px 8px;
            border-radius: 4px;
        }

        .confirm-actions { display: flex; gap: 6px; }

        .confirm-btn {
            flex: 1;
            padding: 8px 12px;
            border: none;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 500;
            cursor: pointer;
        }
        .confirm-btn.cancel { background: rgba(255,255,255,0.05); color: #a1a1aa; }
        .confirm-btn.cancel:hover { background: rgba(255,255,255,0.1); }
        .confirm-btn.danger { background: #dc2626; color: white; }
        .confirm-btn.danger:hover { background: #b91c1c; }

        /* Flash message */
        .flash {
            position: fixed;
            bottom: 6px;
            left: 50%;
            transform: translateX(-50%) translateY(30px);
            padding: 5px 12px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 500;
            opacity: 0;
            transition: all 0.2s ease;
            z-index: 100;
        }
        .flash.show { opacity: 1; transform: translateX(-50%) translateY(0); }
        .flash.success { background: rgba(34, 197, 94, 0.15); color: #22c55e; }
        .flash.error { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
    </style>
</head>
<body>
    <div class="wrapper">
        <div class="control-panel" id="controlPanel">
            <div class="nodes">
                <div class="node" id="node01" onclick="toggleNode('node01')">
                    <span class="node-dot unknown" id="node01Dot"></span>
                    <span class="node-name">Node 01</span>
                    <span class="node-ip">192.168.20.20</span>
                    <svg class="node-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                </div>
                <div class="node" id="node02" onclick="toggleNode('node02')">
                    <span class="node-dot unknown" id="node02Dot"></span>
                    <span class="node-name">Node 02</span>
                    <span class="node-ip">192.168.20.21</span>
                    <svg class="node-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                </div>
                <div class="node" id="node03" onclick="toggleNode('node03')">
                    <span class="node-dot unknown" id="node03Dot"></span>
                    <span class="node-name">Node 03</span>
                    <span class="node-ip">192.168.20.22</span>
                    <svg class="node-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                </div>
            </div>

            <div class="actions">
                <button class="btn wake" id="wolBtn" onclick="sendWol()" title="Wake on LAN">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
                    <span>Wake</span>
                </button>
                <button class="btn shutdown" id="shutdownBtn" onclick="confirmShutdown()" title="Shutdown">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18.36 6.64a9 9 0 1 1-12.73 0"/><line x1="12" y1="2" x2="12" y2="12"/></svg>
                    <span>Off</span>
                </button>
                <button class="btn backup" id="backupBtn" onclick="triggerBackup()" title="Trigger Backup">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                    <span>Backup</span>
                </button>
            </div>
        </div>

        <div class="confirm-panel" id="confirmPanel">
            <div class="confirm-title" id="confirmTitle">Shutdown selected nodes?</div>
            <div class="confirm-nodes" id="confirmNodes"></div>
            <div class="confirm-actions">
                <button class="confirm-btn cancel" onclick="cancelConfirm()">Cancel</button>
                <button class="confirm-btn danger" onclick="executeShutdown()">Shutdown</button>
            </div>
        </div>
    </div>

    <div class="flash" id="flash"></div>

    <script>
        const API_BASE = '';
        let selectedNodes = new Set();
        let pendingShutdownNodes = [];

        function toggleNode(nodeId) {
            const el = document.getElementById(nodeId);
            if (selectedNodes.has(nodeId)) {
                selectedNodes.delete(nodeId);
                el.classList.remove('selected');
            } else {
                selectedNodes.add(nodeId);
                el.classList.add('selected');
            }
        }

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
            if (btn) btn.disabled = loading;
        }

        function showFlash(message, type) {
            const flash = document.getElementById('flash');
            flash.textContent = message;
            flash.className = 'flash ' + type + ' show';
            setTimeout(() => flash.classList.remove('show'), 3000);
        }

        async function sendWol() {
            const nodes = selectedNodes.size > 0 ? Array.from(selectedNodes) : ['node01', 'node02', 'node03'];
            setLoading('wolBtn', 'wolStatus', true);
            try {
                const resp = await fetch(API_BASE + '/wol', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ nodes: nodes })
                });
                const data = await resp.json();
                if (data.success) {
                    showFlash('WoL sent to ' + nodes.length + ' node(s)', 'success');
                }
                pollOperation('wol', 'wolStatus');
            } catch (e) {
                showFlash('WoL failed', 'error');
                document.getElementById('wolBtn').disabled = false;
            }
        }

        function confirmShutdown() {
            const nodes = selectedNodes.size > 0 ? Array.from(selectedNodes) : ['node01', 'node02', 'node03'];
            pendingShutdownNodes = nodes;

            const isAll = nodes.length === 3;
            document.getElementById('confirmTitle').textContent = isAll ? 'Shutdown all nodes?' : 'Shutdown selected?';
            document.getElementById('confirmNodes').innerHTML = nodes.map(n =>
                '<span class="confirm-node">' + n.toUpperCase().replace('NODE0', 'N') + '</span>'
            ).join('');

            document.getElementById('controlPanel').classList.add('hidden');
            document.getElementById('confirmPanel').classList.add('active');
        }

        function cancelConfirm() {
            document.getElementById('confirmPanel').classList.remove('active');
            document.getElementById('controlPanel').classList.remove('hidden');
            pendingShutdownNodes = [];
        }

        async function executeShutdown() {
            const nodes = pendingShutdownNodes;
            cancelConfirm();
            setLoading('shutdownBtn', 'shutdownStatus', true);
            try {
                const resp = await fetch(API_BASE + '/shutdown?confirm=true', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ nodes: nodes })
                });
                const data = await resp.json();
                if (data.success) {
                    showFlash('Shutdown initiated for ' + nodes.length + ' node(s)', 'success');
                }
                pollOperation('shutdown', 'shutdownStatus');
                selectedNodes.clear();
                document.querySelectorAll('.node.selected').forEach(el => el.classList.remove('selected'));
            } catch (e) {
                showFlash('Shutdown failed', 'error');
                document.getElementById('shutdownBtn').disabled = false;
            }
        }

        async function triggerBackup() {
            setLoading('backupBtn', 'backupStatus', true);
            try {
                const resp = await fetch(API_BASE + '/backup', { method: 'POST' });
                const data = await resp.json();
                if (data.success) {
                    showFlash('Backup job started', 'success');
                }
                pollOperation('backup', 'backupStatus');
            } catch (e) {
                showFlash('Backup trigger failed', 'error');
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
                        document.getElementById(statusId).textContent = '';
                        document.getElementById(opType + 'Btn').disabled = false;
                        showFlash(opType + ' operation failed', 'error');
                    } else {
                        setTimeout(check, 3000);
                    }
                } catch (e) {
                    document.getElementById(statusId).textContent = '';
                    document.getElementById(opType + 'Btn').disabled = false;
                }
            };
            setTimeout(check, 2000);
        }

        // Keyboard shortcut: Escape to cancel
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') cancelConfirm();
        });

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


def wol_nodes_async(nodes):
    """Wake specified nodes asynchronously."""
    global operation_status
    operation_status["wol"] = {
        "status": "running",
        "message": f"Sending Wake-on-LAN to {len(nodes)} node(s)...",
        "timestamp": datetime.now().isoformat()
    }

    results = {}
    for node in nodes:
        if node in PROXMOX_NODES:
            info = PROXMOX_NODES[node]
            success = send_wol_packet(info["mac"])
            results[node] = "WoL sent" if success else "Failed"
            time.sleep(0.5)  # Small delay between packets

    # Wait and check if nodes come online
    time.sleep(30)
    online_count = 0
    for node in nodes:
        if node in PROXMOX_NODES:
            info = PROXMOX_NODES[node]
            if check_node_online(info["ip"]):
                results[node] = "Online"
                online_count += 1

    operation_status["wol"] = {
        "status": "completed",
        "message": f"{online_count}/{len(nodes)} nodes online",
        "results": results,
        "timestamp": datetime.now().isoformat()
    }


def shutdown_nodes_async(nodes):
    """Shutdown specified nodes asynchronously (reverse order for safety)."""
    global operation_status
    operation_status["shutdown"] = {
        "status": "running",
        "message": f"Initiating shutdown for {len(nodes)} node(s)...",
        "timestamp": datetime.now().isoformat()
    }

    results = {}
    # Shutdown in reverse order (node03 -> node02 -> node01) for nodes that are selected
    all_nodes_order = ["node03", "node02", "node01"]
    shutdown_order = [n for n in all_nodes_order if n in nodes]

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

                # Initiate node shutdown using systemctl poweroff (more reliable on Proxmox)
                # Use nohup and background to ensure command executes even after SSH disconnects
                stdin, stdout, stderr = client.exec_command(
                    "nohup sh -c 'sleep 2 && systemctl poweroff' > /dev/null 2>&1 &"
                )
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
        "message": f"Shutdown completed for {len(shutdown_order)} node(s)",
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
    """Wake selected Proxmox nodes via Wake-on-LAN."""
    if operation_status["wol"]["status"] == "running":
        return jsonify({
            "success": False,
            "message": "WoL operation already in progress"
        }), 409

    # Get selected nodes from request body, default to all
    data = request.get_json() or {}
    selected_nodes = data.get("nodes", list(PROXMOX_NODES.keys()))

    # Validate node names
    valid_nodes = [n for n in selected_nodes if n in PROXMOX_NODES]
    if not valid_nodes:
        return jsonify({
            "success": False,
            "message": "No valid nodes specified"
        }), 400

    # Start async operation
    thread = threading.Thread(target=wol_nodes_async, args=(valid_nodes,))
    thread.start()

    return jsonify({
        "success": True,
        "message": f"Wake-on-LAN initiated for {len(valid_nodes)} node(s)",
        "nodes": valid_nodes
    })


@app.route("/shutdown", methods=["POST"])
def shutdown_nodes():
    """Shutdown selected Proxmox nodes gracefully."""
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

    # Get selected nodes from request body, default to all
    data = request.get_json() or {}
    selected_nodes = data.get("nodes", list(PROXMOX_NODES.keys()))

    # Validate node names
    valid_nodes = [n for n in selected_nodes if n in PROXMOX_NODES]
    if not valid_nodes:
        return jsonify({
            "success": False,
            "message": "No valid nodes specified"
        }), 400

    # Calculate shutdown order (reverse for safety)
    all_nodes_order = ["node03", "node02", "node01"]
    shutdown_order = [n for n in all_nodes_order if n in valid_nodes]

    # Start async operation
    thread = threading.Thread(target=shutdown_nodes_async, args=(valid_nodes,))
    thread.start()

    return jsonify({
        "success": True,
        "message": f"Shutdown sequence initiated for {len(valid_nodes)} node(s)",
        "nodes": valid_nodes,
        "order": shutdown_order
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

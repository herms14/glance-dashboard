#!/usr/bin/env python3
"""
Proxmox Nodes API - Auto-discovers nodes from Prometheus
Returns node status for Glance dashboard
"""

from flask import Flask, jsonify
import requests
import time
import re

app = Flask(__name__)

PROMETHEUS_URL = "http://192.168.40.13:9090"
CACHE_TTL = 30
cache = {"data": None, "timestamp": 0}


def get_node_ip(node_name):
    """Convert node name to IP (node01 -> 192.168.20.20)."""
    match = re.search(r"node(\d+)", node_name)
    if match:
        node_num = int(match.group(1))
        return f"192.168.20.{19 + node_num}"
    return ""


def get_proxmox_nodes():
    """Query Prometheus for Proxmox node status."""
    now = time.time()

    if cache["data"] and (now - cache["timestamp"]) < CACHE_TTL:
        return cache["data"]

    try:
        # Query for node up status from PVE exporter (deduplicated)
        query = 'max by(id) (pve_up{id=~"node/.*"})'
        resp = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": query},
            timeout=5
        )
        resp.raise_for_status()
        results = resp.json().get("data", {}).get("result", [])

        nodes = []
        for result in results:
            metric = result.get("metric", {})
            node_id = metric.get("id", "")  # e.g., "node/node01"
            value = result.get("value", [0, "0"])[1]

            node_name = node_id.replace("node/", "") if node_id else "unknown"
            ip = get_node_ip(node_name)

            nodes.append({
                "name": node_name,
                "ip": ip,
                "status": "online" if value == "1" else "offline",
                "url": f"https://{ip}:8006" if ip else "#"
            })

        sorted_nodes = sorted(nodes, key=lambda x: x["name"])

        cache["data"] = sorted_nodes
        cache["timestamp"] = now

        return sorted_nodes

    except Exception as e:
        print(f"Error querying Prometheus: {e}")
        return cache.get("data", [])


@app.route("/")
@app.route("/api/nodes")
def nodes():
    """Return Proxmox nodes status."""
    return jsonify(get_proxmox_nodes())


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5061, debug=False)

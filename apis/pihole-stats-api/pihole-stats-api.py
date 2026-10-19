#!/usr/bin/env python3
from flask import Flask, jsonify
import requests
import os
import time

app = Flask(__name__)

PIHOLE_URL = os.environ.get("PIHOLE_URL", "http://192.168.90.53")
PIHOLE_PASSWORD = os.environ["PIHOLE_PASSWORD"]

cache = {"data": None, "timestamp": 0}
CACHE_TTL = 60

def get_session():
    try:
        resp = requests.post(
            f"{PIHOLE_URL}/api/auth",
            json={"password": PIHOLE_PASSWORD},
            timeout=10
        )
        if resp.ok:
            data = resp.json()
            if data.get("session", {}).get("valid"):
                return data["session"]["sid"]
    except Exception as e:
        print(f"Auth error: {e}")
    return None

def get_stats():
    now = time.time()
    if cache["data"] and (now - cache["timestamp"]) < CACHE_TTL:
        return cache["data"]
    
    sid = get_session()
    if not sid:
        return {"error": "Authentication failed"}
    
    try:
        resp = requests.get(
            f"{PIHOLE_URL}/api/stats/summary",
            headers={"sid": sid},
            timeout=10
        )
        if resp.ok:
            cache["data"] = resp.json()
            cache["timestamp"] = now
            return cache["data"]
    except Exception as e:
        print(f"Stats error: {e}")
    
    return {"error": "Failed to fetch stats"}

@app.route("/api/pihole/stats")
def pihole_stats():
    return jsonify(get_stats())

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5055)

#!/usr/bin/env python3
"""
Media Stats API Aggregator
Combines Radarr and Sonarr stats into a single endpoint for Glance dashboard.
Returns all media stats in a format suitable for the 3x3 tile grid layout.
"""

import os
import requests
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Configuration from environment variables
RADARR_URL = os.getenv('RADARR_URL', 'http://192.168.40.11:7878')
RADARR_API_KEY = os.getenv('RADARR_API_KEY', '')
SONARR_URL = os.getenv('SONARR_URL', 'http://192.168.40.11:8989')
SONARR_API_KEY = os.getenv('SONARR_API_KEY', '')


def fetch_radarr_stats():
    """Fetch all Radarr statistics."""
    headers = {'X-Api-Key': RADARR_API_KEY}
    stats = {
        'wanted': 0,
        'downloading': 0,
        'downloaded': 0
    }

    try:
        # Wanted movies
        resp = requests.get(
            f'{RADARR_URL}/api/v3/wanted/missing',
            headers=headers,
            params={'pageSize': 1},
            timeout=5
        )
        if resp.ok:
            stats['wanted'] = resp.json().get('totalRecords', 0)

        # Downloading
        resp = requests.get(
            f'{RADARR_URL}/api/v3/queue',
            headers=headers,
            params={'pageSize': 1},
            timeout=5
        )
        if resp.ok:
            stats['downloading'] = resp.json().get('totalRecords', 0)

        # Downloaded (movies with files)
        resp = requests.get(
            f'{RADARR_URL}/api/v3/movie',
            headers=headers,
            timeout=10
        )
        if resp.ok:
            movies = resp.json()
            stats['downloaded'] = sum(1 for m in movies if m.get('hasFile', False))

    except requests.RequestException as e:
        print(f"Radarr error: {e}")

    return stats


def fetch_sonarr_stats():
    """Fetch all Sonarr statistics."""
    headers = {'X-Api-Key': SONARR_API_KEY}
    stats = {
        'wanted': 0,
        'downloading': 0,
        'downloaded': 0
    }

    try:
        # Wanted episodes
        resp = requests.get(
            f'{SONARR_URL}/api/v3/wanted/missing',
            headers=headers,
            params={'pageSize': 1},
            timeout=5
        )
        if resp.ok:
            stats['wanted'] = resp.json().get('totalRecords', 0)

        # Downloading
        resp = requests.get(
            f'{SONARR_URL}/api/v3/queue',
            headers=headers,
            params={'pageSize': 1},
            timeout=5
        )
        if resp.ok:
            stats['downloading'] = resp.json().get('totalRecords', 0)

        # Downloaded episodes
        resp = requests.get(
            f'{SONARR_URL}/api/v3/series',
            headers=headers,
            timeout=10
        )
        if resp.ok:
            series = resp.json()
            stats['downloaded'] = sum(
                s.get('statistics', {}).get('episodeFileCount', 0)
                for s in series
            )

    except requests.RequestException as e:
        print(f"Sonarr error: {e}")

    return stats


@app.route('/api/stats')
def get_stats():
    """Return combined media stats for Glance dashboard grid."""
    radarr = fetch_radarr_stats()
    sonarr = fetch_sonarr_stats()

    # Return structured data for the 6-tile grid (3x2)
    return jsonify({
        'stats': [
            {
                'label': 'WANTED MOVIES',
                'value': radarr['wanted'],
                'color': '#f59e0b',
                'icon': 'movie'
            },
            {
                'label': 'MOVIES DOWNLOADING',
                'value': radarr['downloading'],
                'color': '#3b82f6',
                'icon': 'download'
            },
            {
                'label': 'MOVIES DOWNLOADED',
                'value': radarr['downloaded'],
                'color': '#22c55e',
                'icon': 'check'
            },
            {
                'label': 'WANTED EPISODES',
                'value': sonarr['wanted'],
                'color': '#ef4444',
                'icon': 'tv'
            },
            {
                'label': 'EPISODES DOWNLOADING',
                'value': sonarr['downloading'],
                'color': '#8b5cf6',
                'icon': 'download'
            },
            {
                'label': 'EPISODES DOWNLOADED',
                'value': sonarr['downloaded'],
                'color': '#06b6d4',
                'icon': 'check'
            }
        ],
        'radarr': radarr,
        'sonarr': sonarr
    })


@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5054, debug=False)

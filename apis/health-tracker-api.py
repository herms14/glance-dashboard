#!/usr/bin/env python3
"""
Health Tracker API for Glance Dashboard
Integrates Strava activities and manual weight logging.
Serves HTML pages for iframe embedding and JSON for custom-api widgets.
Runs on docker-vm-core-utilities01 (192.168.40.13) port 5062
"""

from flask import Flask, jsonify, request, render_template_string, redirect
from flask_cors import CORS
import json
import os
import time
import requests
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

# Configuration paths
CONFIG_DIR = os.environ.get('CONFIG_DIR', '/app/config')
TOKENS_FILE = os.path.join(CONFIG_DIR, 'strava_tokens.json')
ACTIVITIES_FILE = os.path.join(CONFIG_DIR, 'activities_cache.json')
WEIGHT_FILE = os.path.join(CONFIG_DIR, 'weight_log.json')
SETTINGS_FILE = os.path.join(CONFIG_DIR, 'settings.json')

STRAVA_AUTH_URL = 'https://www.strava.com/oauth/authorize'
STRAVA_TOKEN_URL = 'https://www.strava.com/oauth/token'
STRAVA_API_URL = 'https://www.strava.com/api/v3'

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_json(filepath, default=None):
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}

def save_json(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

def get_settings():
    return load_json(SETTINGS_FILE, {
        'timezone': 'Asia/Manila',
        'cache_ttl_minutes': 30,
        'calendar_days': 60,
        'weight_unit': 'kg',
        'goal_weight': None
    })

def get_tokens():
    return load_json(TOKENS_FILE, {})

def save_tokens(tokens):
    save_json(TOKENS_FILE, tokens)

def strava_connected():
    tokens = get_tokens()
    return bool(tokens.get('access_token') and tokens.get('refresh_token'))

def refresh_token_if_needed():
    """Auto-refresh Strava token if within 10 min of expiry."""
    tokens = get_tokens()
    if not tokens.get('refresh_token'):
        return None
    expires_at = tokens.get('expires_at', 0)
    if time.time() > expires_at - 600:
        try:
            resp = requests.post(STRAVA_TOKEN_URL, data={
                'client_id': tokens.get('client_id'),
                'client_secret': tokens.get('client_secret'),
                'grant_type': 'refresh_token',
                'refresh_token': tokens['refresh_token']
            }, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                tokens['access_token'] = data['access_token']
                tokens['refresh_token'] = data['refresh_token']
                tokens['expires_at'] = data['expires_at']
                save_tokens(tokens)
                return tokens['access_token']
        except Exception as e:
            app.logger.error(f'Token refresh failed: {e}')
            return tokens.get('access_token')
    return tokens.get('access_token')

def strava_get(path, params=None):
    """Make authenticated GET to Strava API."""
    token = refresh_token_if_needed()
    if not token:
        return None
    headers = {'Authorization': f'Bearer {token}'}
    resp = requests.get(f'{STRAVA_API_URL}{path}', headers=headers,
                        params=params, timeout=20)
    if resp.status_code == 200:
        return resp.json()
    app.logger.error(f'Strava API {path} returned {resp.status_code}')
    return None

def sync_activities():
    """Fetch last N days of activities from Strava, cache them."""
    settings = get_settings()
    cache = load_json(ACTIVITIES_FILE, {'last_fetched': 0, 'activities': []})
    ttl = settings.get('cache_ttl_minutes', 30) * 60
    if time.time() - cache.get('last_fetched', 0) < ttl:
        return cache['activities']

    days = settings.get('calendar_days', 60)
    after = int((datetime.now() - timedelta(days=days)).timestamp())
    page = 1
    all_acts = []
    while True:
        data = strava_get('/athlete/activities', {
            'after': after, 'per_page': 100, 'page': page
        })
        if not data:
            break
        all_acts.extend(data)
        if len(data) < 100:
            break
        page += 1

    processed = []
    for a in all_acts:
        processed.append({
            'id': a.get('id'),
            'name': a.get('name', ''),
            'type': a.get('type', 'Workout'),
            'sport_type': a.get('sport_type', a.get('type', 'Workout')),
            'date': a.get('start_date_local', '')[:10],
            'start_time': a.get('start_date_local', ''),
            'distance_m': a.get('distance', 0),
            'moving_time_s': a.get('moving_time', 0),
            'elapsed_time_s': a.get('elapsed_time', 0),
            'elevation_gain': a.get('total_elevation_gain', 0),
            'average_speed': a.get('average_speed', 0),
            'max_speed': a.get('max_speed', 0),
            'average_heartrate': a.get('average_heartrate'),
            'max_heartrate': a.get('max_heartrate'),
            'calories': a.get('calories', 0),
            'kudos': a.get('kudos_count', 0),
        })

    cache = {'last_fetched': time.time(), 'activities': processed}
    save_json(ACTIVITIES_FILE, cache)
    return processed

def get_weight_log():
    return load_json(WEIGHT_FILE, {'unit': 'kg', 'goal_weight': None, 'entries': []})

def save_weight_log(data):
    save_json(WEIGHT_FILE, data)

def format_duration(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    if h > 0:
        return f'{h}h {m}m'
    return f'{m}m'

def format_distance(meters):
    if meters >= 1000:
        return f'{meters / 1000:.1f} km'
    return f'{int(meters)} m'

def activity_icon(activity_type):
    icons = {
        'Ride': '\U0001f6b4', 'VirtualRide': '\U0001f6b4',
        'Run': '\U0001f3c3', 'VirtualRun': '\U0001f3c3',
        'Swim': '\U0001f3ca',
        'Walk': '\U0001f6b6', 'Hike': '\u26f0\ufe0f',
        'WeightTraining': '\U0001f4aa', 'Workout': '\U0001f4aa',
        'Yoga': '\U0001f9d8', 'Crossfit': '\U0001f3cb\ufe0f',
        'Elliptical': '\U0001f3cb\ufe0f', 'StairStepper': '\U0001f3cb\ufe0f',
    }
    return icons.get(activity_type, '\U0001f3c5')

# ---------------------------------------------------------------------------
# JSON API Endpoints
# ---------------------------------------------------------------------------

@app.route('/api/health')
def health():
    return jsonify({'status': 'healthy', 'service': 'health-tracker-api'})

@app.route('/api/strava/status')
def strava_status():
    tokens = get_tokens()
    connected = strava_connected()
    cache = load_json(ACTIVITIES_FILE, {})
    last_sync = cache.get('last_fetched', 0)
    return jsonify({
        'connected': connected,
        'athlete': tokens.get('athlete', {}).get('firstname', '') + ' ' + tokens.get('athlete', {}).get('lastname', '') if connected else '',
        'last_sync': datetime.fromtimestamp(last_sync).strftime('%Y-%m-%d %H:%M') if last_sync else 'Never',
        'activities_cached': len(cache.get('activities', [])),
    })

@app.route('/api/strava/authorize')
def strava_authorize():
    tokens = get_tokens()
    client_id = tokens.get('client_id')
    if not client_id:
        return jsonify({'error': 'client_id not configured in strava_tokens.json'}), 400
    default_callback = os.environ.get('STRAVA_CALLBACK_URL',
        'https://health-api.hrmsmrflrii.xyz/api/strava/callback')
    callback_url = request.args.get('callback', default_callback)
    url = (f'{STRAVA_AUTH_URL}?client_id={client_id}'
           f'&redirect_uri={callback_url}'
           f'&response_type=code&scope=read,activity:read_all'
           f'&approval_prompt=auto')
    return redirect(url)

@app.route('/api/strava/callback')
def strava_callback():
    code = request.args.get('code')
    if not code:
        return jsonify({'error': 'No authorization code received'}), 400
    tokens = get_tokens()
    try:
        resp = requests.post(STRAVA_TOKEN_URL, data={
            'client_id': tokens.get('client_id'),
            'client_secret': tokens.get('client_secret'),
            'code': code,
            'grant_type': 'authorization_code'
        }, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            tokens['access_token'] = data['access_token']
            tokens['refresh_token'] = data['refresh_token']
            tokens['expires_at'] = data['expires_at']
            tokens['athlete'] = data.get('athlete', {})
            save_tokens(tokens)
            sync_activities()
            return redirect('/page/setup?success=1')
        return jsonify({'error': f'Token exchange failed: {resp.status_code}',
                        'detail': resp.text}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/activities/weekly')
def activities_weekly():
    activities = sync_activities() if strava_connected() else []
    today = datetime.now().date()
    seven_days_ago = today - timedelta(days=6)  # Rolling 7 days including today
    week_acts = [a for a in activities
                 if a.get('date') and a['date'] >= str(seven_days_ago)]
    active_days = len(set(a['date'] for a in week_acts))
    rides = sum(1 for a in week_acts if a['type'] in ('Ride', 'VirtualRide'))
    gym = sum(1 for a in week_acts
              if a['type'] in ('WeightTraining', 'Workout', 'Crossfit'))
    total_time = sum(a.get('moving_time_s', 0) for a in week_acts)
    total_dist = sum(a.get('distance_m', 0) for a in week_acts)
    total_cal = sum(a.get('calories', 0) for a in week_acts)

    return jsonify({
        'active_days': active_days,
        'total_activities': len(week_acts),
        'rides': rides,
        'gym_sessions': gym,
        'total_time': format_duration(total_time),
        'total_time_s': total_time,
        'total_distance': format_distance(total_dist),
        'total_distance_m': total_dist,
        'total_calories': total_cal,
        'week_start': str(seven_days_ago),
        'status_color': '#22c55e' if active_days >= 4 else '#f59e0b' if active_days >= 2 else '#ef4444',
    })

@app.route('/api/activities/calendar')
def activities_calendar():
    activities = sync_activities() if strava_connected() else []
    settings = get_settings()
    days = settings.get('calendar_days', 60)
    today = datetime.now().date()

    day_map = {}
    for a in activities:
        d = a.get('date')
        if d:
            day_map.setdefault(d, []).append(a['type'])

    calendar = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        ds = str(d)
        acts = day_map.get(ds, [])
        calendar.append({
            'date': ds,
            'weekday': d.strftime('%a'),
            'count': len(acts),
            'types': acts,
        })
    return jsonify({'days': calendar, 'total_days': days})

@app.route('/api/weight', methods=['GET'])
def weight_get():
    log = get_weight_log()
    entries = sorted(log.get('entries', []), key=lambda e: e['date'])
    goal = log.get('goal_weight')
    unit = log.get('unit', 'kg')
    current = entries[-1]['weight'] if entries else None
    first = entries[0]['weight'] if entries else None

    # weekly change
    week_ago = str((datetime.now() - timedelta(days=7)).date())
    week_entries = [e for e in entries if e['date'] <= week_ago]
    week_weight = week_entries[-1]['weight'] if week_entries else current
    weekly_change = round(current - week_weight, 1) if current and week_weight else None

    return jsonify({
        'current_weight': current,
        'start_weight': first,
        'goal_weight': goal,
        'unit': unit,
        'total_change': round(current - first, 1) if current and first else None,
        'weekly_change': weekly_change,
        'entries': entries[-90:],  # last 90 entries
        'entry_count': len(entries),
    })

@app.route('/api/weight', methods=['POST'])
def weight_post():
    data = request.get_json()
    if not data or 'weight' not in data:
        return jsonify({'error': 'weight is required'}), 400
    weight = float(data['weight'])
    date = data.get('date', str(datetime.now().date()))
    note = data.get('note', '')

    log = get_weight_log()
    entries = log.get('entries', [])
    # Update existing entry for same date or append
    for e in entries:
        if e['date'] == date:
            e['weight'] = weight
            e['note'] = note
            break
    else:
        entries.append({'date': date, 'weight': weight, 'note': note})
    log['entries'] = entries
    if data.get('goal_weight') is not None:
        log['goal_weight'] = float(data['goal_weight'])
    save_weight_log(log)
    return jsonify({'status': 'ok', 'date': date, 'weight': weight})

@app.route('/api/weight/<date>', methods=['DELETE'])
def weight_delete(date):
    log = get_weight_log()
    entries = log.get('entries', [])
    log['entries'] = [e for e in entries if e['date'] != date]
    save_weight_log(log)
    return jsonify({'status': 'ok', 'deleted': date})

@app.route('/api/stats')
def athlete_stats():
    """Fetch athlete stats from Strava (recent, ytd, all-time) plus best efforts from cached activities."""
    if not strava_connected():
        return jsonify({'error': 'Strava not connected'}), 400

    tokens = get_tokens()
    athlete_id = tokens.get('athlete', {}).get('id')
    if not athlete_id:
        return jsonify({'error': 'No athlete ID'}), 400

    stats = strava_get(f'/athletes/{athlete_id}/stats')
    if not stats:
        return jsonify({'error': 'Failed to fetch stats'}), 502

    activities = sync_activities()

    # Best efforts from cached activities (rides)
    rides = [a for a in activities if a.get('type') in ('Ride', 'VirtualRide')]
    longest_ride = max((a.get('distance_m', 0) for a in rides), default=0)
    biggest_climb = max((a.get('elevation_gain', 0) for a in rides), default=0)
    total_elev = sum(a.get('elevation_gain', 0) for a in rides)

    def fmt_totals(t):
        return {
            'count': t.get('count', 0),
            'distance_km': round(t.get('distance', 0) / 1000, 1),
            'elevation_m': round(t.get('elevation_gain', 0)),
            'time': format_duration(t.get('moving_time', 0)),
            'time_s': t.get('moving_time', 0),
        }

    return jsonify({
        'recent_rides': fmt_totals(stats.get('recent_ride_totals', {})),
        'ytd_rides': fmt_totals(stats.get('ytd_ride_totals', {})),
        'all_rides': fmt_totals(stats.get('all_ride_totals', {})),
        'recent_runs': fmt_totals(stats.get('recent_run_totals', {})),
        'ytd_runs': fmt_totals(stats.get('ytd_run_totals', {})),
        'all_runs': fmt_totals(stats.get('all_run_totals', {})),
        'best_efforts': {
            'longest_ride_km': round(longest_ride / 1000, 1),
            'biggest_climb_m': round(biggest_climb),
            'total_elevation_m': round(total_elev),
        },
    })

# ---------------------------------------------------------------------------
# HTML Pages (for Glance iframe embedding)
# ---------------------------------------------------------------------------

COMMON_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', sans-serif;
    background: rgb(15, 15, 20) !important;
    color: #a1a1aa;
    overflow-x: hidden;
}
.wrapper { padding: 12px; }
a { color: #60a5fa; text-decoration: none; }
a:hover { text-decoration: underline; }
"""

@app.route('/page/calendar')
def page_calendar():
    activities = sync_activities() if strava_connected() else []
    settings = get_settings()
    days = settings.get('calendar_days', 60)
    today = datetime.now().date()

    day_map = {}
    for a in activities:
        d = a.get('date')
        if d:
            day_map.setdefault(d, []).append(a)

    cells = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        ds = str(d)
        count = len(day_map.get(ds, []))
        cells.append({'date': ds, 'count': count, 'weekday': d.weekday(),
                      'label': d.strftime('%b %d')})

    return render_template_string(CALENDAR_HTML, cells=cells, today=str(today))

CALENDAR_HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
""" + COMMON_CSS + """
.title { font-size: 13px; font-weight: 600; color: #d4d4d8; margin-bottom: 10px; }
.grid { display: flex; flex-wrap: wrap; gap: 3px; }
.cell {
    width: 18px; height: 18px; border-radius: 3px;
    background: rgba(255,255,255,0.04);
    position: relative; cursor: default;
}
.cell.c1 { background: rgba(34,197,94,0.3); }
.cell.c2 { background: rgba(34,197,94,0.55); }
.cell.c3 { background: rgba(34,197,94,0.8); }
.cell.today { outline: 2px solid #60a5fa; outline-offset: -1px; }
.cell:hover .tip {
    display: block;
}
.tip {
    display: none; position: absolute; bottom: 22px; left: 50%;
    transform: translateX(-50%); background: #27272a; color: #d4d4d8;
    font-size: 10px; padding: 3px 6px; border-radius: 4px;
    white-space: nowrap; z-index: 10; pointer-events: none;
}
.legend { display: flex; align-items: center; gap: 6px; margin-top: 8px; font-size: 10px; color: #71717a; }
.legend-box { width: 12px; height: 12px; border-radius: 2px; }
.stats { font-size: 11px; color: #71717a; margin-top: 6px; }
.stats span { color: #22c55e; font-weight: 600; }
</style></head><body>
<div class="wrapper">
    <div class="title">Exercise Calendar (60 days)</div>
    <div class="grid">
        {% for c in cells %}
        <div class="cell {{ 'c1' if c.count == 1 else 'c2' if c.count == 2 else 'c3' if c.count >= 3 else '' }} {{ 'today' if c.date == today else '' }}">
            <span class="tip">{{ c.label }}: {{ c.count }} activit{{ 'y' if c.count == 1 else 'ies' }}</span>
        </div>
        {% endfor %}
    </div>
    <div class="legend">
        <span>Less</span>
        <div class="legend-box" style="background:rgba(255,255,255,0.04)"></div>
        <div class="legend-box" style="background:rgba(34,197,94,0.3)"></div>
        <div class="legend-box" style="background:rgba(34,197,94,0.55)"></div>
        <div class="legend-box" style="background:rgba(34,197,94,0.8)"></div>
        <span>More</span>
    </div>
    {% set active = cells|selectattr('count','gt', 0)|list|length %}
    <div class="stats"><span>{{ active }}</span> active days out of {{ cells|length }}</div>
</div>
</body></html>"""

@app.route('/page/weight')
def page_weight():
    log = get_weight_log()
    entries = sorted(log.get('entries', []), key=lambda e: e['date'])
    goal = log.get('goal_weight')
    unit = log.get('unit', 'kg')
    return render_template_string(WEIGHT_HTML, entries=entries, goal=goal,
                                  unit=unit, entries_json=json.dumps(entries))

WEIGHT_HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
""" + COMMON_CSS + """
.chart-wrap { position: relative; height: 220px; margin-bottom: 14px; }
canvas { width: 100% !important; }
.form-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
input, button {
    font-family: inherit; font-size: 12px; border: none; border-radius: 6px;
    padding: 6px 10px; outline: none;
}
input { background: rgba(255,255,255,0.06); color: #d4d4d8; width: 90px; }
input:focus { background: rgba(255,255,255,0.1); }
button {
    background: rgba(34,197,94,0.2); color: #22c55e; cursor: pointer;
    font-weight: 600;
}
button:hover { background: rgba(34,197,94,0.3); }
.msg { font-size: 11px; margin-top: 6px; min-height: 16px; }
.msg.ok { color: #22c55e; }
.msg.err { color: #ef4444; }
.stats-row { display: flex; gap: 16px; margin-bottom: 10px; font-size: 11px; }
.stat-label { color: #71717a; }
.stat-val { color: #d4d4d8; font-weight: 600; }
.stat-change { font-weight: 600; }
.stat-change.down { color: #22c55e; }
.stat-change.up { color: #ef4444; }
.no-data { color: #52525b; text-align: center; padding: 40px 0; font-size: 13px; }
</style></head><body>
<div class="wrapper">
    {% if entries %}
    <div class="stats-row">
        <div><span class="stat-label">Current </span><span class="stat-val">{{ entries[-1].weight }} {{ unit }}</span></div>
        {% if goal %}<div><span class="stat-label">Goal </span><span class="stat-val">{{ goal }} {{ unit }}</span></div>{% endif %}
        {% if entries|length > 1 %}
        {% set diff = entries[-1].weight - entries[0].weight %}
        <div><span class="stat-label">Total </span><span class="stat-change {{ 'down' if diff < 0 else 'up' }}">{{ '%+.1f'|format(diff) }} {{ unit }}</span></div>
        {% endif %}
    </div>
    <div class="chart-wrap"><canvas id="wChart"></canvas></div>
    {% else %}
    <div class="no-data">No weight entries yet. Log your first entry below.</div>
    {% endif %}
    <div class="form-row">
        <input type="number" id="wVal" placeholder="{{ unit }}" step="0.1" min="0">
        <input type="date" id="wDate" value="{{ today }}">
        <input type="text" id="wNote" placeholder="Note (optional)" style="width:120px">
        <button onclick="logWeight()">Log</button>
    </div>
    <div class="msg" id="msg"></div>
</div>
<script>
document.getElementById('wDate').value = new Date().toISOString().slice(0,10);
var entriesData = {{ entries_json|safe }};

{% if entries %}
var labels = entriesData.map(e => e.date);
var weights = entriesData.map(e => e.weight);
var goalVal = {{ goal if goal else 'null' }};

var datasets = [{
    label: 'Weight',
    data: weights,
    borderColor: '#60a5fa',
    backgroundColor: 'rgba(96,165,250,0.1)',
    fill: true,
    tension: 0.3,
    pointRadius: weights.length > 30 ? 0 : 3,
    pointHoverRadius: 5,
    borderWidth: 2
}];
if (goalVal) {
    datasets.push({
        label: 'Goal',
        data: Array(labels.length).fill(goalVal),
        borderColor: 'rgba(34,197,94,0.5)',
        borderDash: [6,4],
        borderWidth: 1,
        pointRadius: 0,
        fill: false
    });
}
var ctx = document.getElementById('wChart').getContext('2d');
new Chart(ctx, {
    type: 'line',
    data: { labels: labels, datasets: datasets },
    options: {
        responsive: true, maintainAspectRatio: false,
        scales: {
            x: { ticks: { color: '#52525b', font: { size: 10 }, maxTicksLimit: 8 },
                 grid: { color: 'rgba(255,255,255,0.03)' } },
            y: { ticks: { color: '#52525b', font: { size: 10 } },
                 grid: { color: 'rgba(255,255,255,0.05)' } }
        },
        plugins: {
            legend: { display: false },
            tooltip: {
                backgroundColor: '#27272a', titleColor: '#d4d4d8',
                bodyColor: '#a1a1aa', borderColor: '#3f3f46', borderWidth: 1
            }
        }
    }
});
{% endif %}

function logWeight() {
    var w = document.getElementById('wVal').value;
    var d = document.getElementById('wDate').value;
    var n = document.getElementById('wNote').value;
    var msg = document.getElementById('msg');
    if (!w) { msg.className='msg err'; msg.textContent='Enter a weight value'; return; }
    fetch('/api/weight', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({weight: parseFloat(w), date: d, note: n})
    }).then(r => r.json()).then(data => {
        if (data.status === 'ok') {
            msg.className='msg ok'; msg.textContent='Logged ' + w + ' on ' + d;
            setTimeout(() => location.reload(), 800);
        } else {
            msg.className='msg err'; msg.textContent=data.error||'Failed';
        }
    }).catch(e => { msg.className='msg err'; msg.textContent='Error: '+e; });
}
</script>
</body></html>"""

@app.route('/page/activities')
def page_activities():
    activities = sync_activities() if strava_connected() else []
    recent = sorted(activities, key=lambda a: a.get('start_time', ''), reverse=True)[:15]
    return render_template_string(ACTIVITIES_HTML, activities=recent,
                                  connected=strava_connected(),
                                  format_duration=format_duration,
                                  format_distance=format_distance,
                                  activity_icon=activity_icon)

ACTIVITIES_HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
""" + COMMON_CSS + """
.title { font-size: 13px; font-weight: 600; color: #d4d4d8; margin-bottom: 10px; }
.act {
    display: flex; align-items: center; gap: 10px;
    padding: 8px 10px; border-radius: 6px;
    background: rgba(255,255,255,0.02);
    margin-bottom: 4px;
    transition: background 0.15s;
}
.act:hover { background: rgba(255,255,255,0.05); }
.act-icon { font-size: 18px; flex-shrink: 0; width: 28px; text-align: center; }
.act-info { flex: 1; min-width: 0; }
.act-name { font-size: 12px; font-weight: 500; color: #d4d4d8;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.act-meta { font-size: 10px; color: #71717a; margin-top: 2px; }
.act-stats { text-align: right; font-size: 11px; white-space: nowrap; }
.act-dist { color: #60a5fa; font-weight: 600; }
.act-time { color: #71717a; }
.empty { color: #52525b; text-align: center; padding: 30px 0; font-size: 13px; }
</style></head><body>
<div class="wrapper">
    <div class="title">Recent Activities</div>
    {% if not connected %}
    <div class="empty">Connect Strava to see activities</div>
    {% elif not activities %}
    <div class="empty">No activities in the last 60 days</div>
    {% else %}
    {% for a in activities %}
    <div class="act">
        <div class="act-icon">{{ activity_icon(a.type) }}</div>
        <div class="act-info">
            <div class="act-name">{{ a.name }}</div>
            <div class="act-meta">{{ a.type }} &middot; {{ a.date }}</div>
        </div>
        <div class="act-stats">
            {% if a.distance_m > 0 %}
            <div class="act-dist">{{ format_distance(a.distance_m) }}</div>
            {% endif %}
            <div class="act-time">{{ format_duration(a.moving_time_s) }}</div>
        </div>
    </div>
    {% endfor %}
    {% endif %}
</div>
</body></html>"""

@app.route('/page/setup')
def page_setup():
    tokens = get_tokens()
    connected = strava_connected()
    success = request.args.get('success')
    return render_template_string(SETUP_HTML, connected=connected,
                                  tokens=tokens, success=success)

SETUP_HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
""" + COMMON_CSS + """
.card {
    background: rgba(255,255,255,0.03); border-radius: 8px;
    padding: 20px; max-width: 500px; margin: 30px auto;
}
h1 { font-size: 18px; color: #d4d4d8; margin-bottom: 16px; }
.step { margin-bottom: 16px; }
.step-num {
    display: inline-block; width: 22px; height: 22px; line-height: 22px;
    text-align: center; border-radius: 50%; background: rgba(96,165,250,0.2);
    color: #60a5fa; font-size: 11px; font-weight: 700; margin-right: 8px;
}
.step-title { font-size: 13px; color: #d4d4d8; font-weight: 500; }
.step-desc { font-size: 12px; color: #71717a; margin: 6px 0 0 30px; }
code {
    background: rgba(255,255,255,0.06); padding: 2px 6px; border-radius: 4px;
    font-size: 11px; color: #a78bfa;
}
.btn-connect {
    display: inline-block; margin-top: 20px; padding: 10px 24px;
    background: #fc4c02; color: white; border-radius: 6px;
    font-size: 13px; font-weight: 600; text-decoration: none;
    transition: background 0.15s;
}
.btn-connect:hover { background: #e04400; text-decoration: none; }
.status {
    padding: 12px; border-radius: 6px; margin-bottom: 16px; font-size: 13px;
}
.status.ok { background: rgba(34,197,94,0.1); color: #22c55e; }
.status.pending { background: rgba(245,158,11,0.1); color: #f59e0b; }
.status.fresh { background: rgba(96,165,250,0.1); color: #60a5fa; }
</style></head><body>
<div class="wrapper">
    <div class="card">
        <h1>Health Tracker - Strava Setup</h1>

        {% if success %}
        <div class="status fresh">Strava connected successfully! Activities are syncing now.</div>
        {% endif %}

        {% if connected %}
        <div class="status ok">
            Connected as {{ tokens.athlete.firstname }} {{ tokens.athlete.lastname }}
        </div>
        <p style="font-size:12px; color:#71717a;">
            Strava is connected and tokens will auto-refresh. No action needed.
            <br><br>Activities sync every 30 minutes.
            <br>Last sync data is cached in <code>/app/config/activities_cache.json</code>.
        </p>
        {% else %}
        {% if tokens.client_id %}
        <div class="status pending">Client ID configured. Click below to connect.</div>
        {% else %}
        <div class="status pending">Set up your Strava API credentials first.</div>
        {% endif %}

        <div class="step">
            <span class="step-num">1</span>
            <span class="step-title">Create Strava API Application</span>
            <div class="step-desc">
                Go to <a href="https://www.strava.com/settings/api" target="_blank">strava.com/settings/api</a><br>
                Set callback domain to <code>192.168.40.13</code>
            </div>
        </div>

        <div class="step">
            <span class="step-num">2</span>
            <span class="step-title">Add credentials to config</span>
            <div class="step-desc">
                Edit <code>/opt/health-tracker-api/config/strava_tokens.json</code>:<br>
                Set <code>client_id</code> and <code>client_secret</code> from Strava
            </div>
        </div>

        <div class="step">
            <span class="step-num">3</span>
            <span class="step-title">Connect to Strava</span>
            <div class="step-desc">Click the button below to authorize</div>
        </div>

        {% if tokens.client_id %}
        <a class="btn-connect" href="/api/strava/authorize">Connect to Strava</a>
        {% else %}
        <div style="margin-top:20px; font-size:12px; color:#52525b;">
            Add client_id to strava_tokens.json first, then refresh this page.
        </div>
        {% endif %}
        {% endif %}
    </div>
</div>
</body></html>"""

@app.route('/page/stats')
def page_stats():
    return render_template_string(STATS_HTML)

STATS_HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
""" + COMMON_CSS + """
.stats-grid {
    display: grid; grid-template-columns: 1fr 1fr; gap: 16px;
    max-width: 900px; margin: 0 auto;
}
.stat-card {
    background: rgba(255,255,255,0.03); border-radius: 8px; padding: 16px;
}
.stat-card h2 {
    font-size: 13px; font-weight: 600; color: #a1a1aa;
    text-transform: uppercase; letter-spacing: 0.5px;
    margin: 0 0 12px 0; padding-bottom: 8px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
}
.stat-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 6px 0; font-size: 12px;
}
.stat-label { color: #71717a; }
.stat-value { color: #d4d4d8; font-weight: 600; font-variant-numeric: tabular-nums; }
.stat-value.accent { color: #60a5fa; }
.stat-value.green { color: #22c55e; }
.stat-value.orange { color: #fc4c02; }
.loading { color: #52525b; text-align: center; padding: 40px; font-size: 13px; }
.error { color: #ef4444; text-align: center; padding: 40px; font-size: 13px; }
@media (max-width: 600px) {
    .stats-grid { grid-template-columns: 1fr; }
}
</style>
<script>
async function loadStats() {
    const container = document.getElementById('stats-container');
    try {
        const resp = await fetch('/api/stats');
        if (!resp.ok) {
            const err = await resp.json();
            container.innerHTML = '<div class="error">' + (err.error || 'Failed to load stats') + '</div>';
            return;
        }
        const d = await resp.json();

        function statRow(label, value, cls) {
            return '<div class="stat-row"><span class="stat-label">' + label +
                   '</span><span class="stat-value ' + (cls||'') + '">' + value + '</span></div>';
        }

        function rideCard(title, data, cls) {
            if (!data || data.count === 0) return '';
            return '<div class="stat-card"><h2>' + title + '</h2>' +
                statRow('Activities', data.count, cls) +
                statRow('Distance', data.distance_km + ' km', cls) +
                statRow('Elevation', data.elevation_m.toLocaleString() + ' m', cls) +
                statRow('Time', data.time, cls) +
                '</div>';
        }

        let html = '<div class="stats-grid">';

        // Last 4 Weeks
        html += rideCard('Last 4 Weeks - Rides', d.recent_rides, 'accent');

        // Best Efforts
        if (d.best_efforts) {
            html += '<div class="stat-card"><h2>Best Efforts</h2>';
            if (d.best_efforts.longest_ride_km > 0)
                html += statRow('Longest Ride', d.best_efforts.longest_ride_km + ' km', 'orange');
            if (d.best_efforts.biggest_climb_m > 0)
                html += statRow('Biggest Climb', d.best_efforts.biggest_climb_m.toLocaleString() + ' m', 'orange');
            if (d.best_efforts.total_elevation_m > 0)
                html += statRow('Total Elevation', d.best_efforts.total_elevation_m.toLocaleString() + ' m', 'orange');
            html += '</div>';
        }

        // YTD
        html += rideCard(new Date().getFullYear() + ' Year to Date - Rides', d.ytd_rides, 'green');

        // All-Time
        html += rideCard('All-Time - Rides', d.all_rides, '');

        // Runs (if any)
        if (d.ytd_runs && d.ytd_runs.count > 0) {
            html += rideCard(new Date().getFullYear() + ' Year to Date - Runs', d.ytd_runs, 'green');
        }
        if (d.all_runs && d.all_runs.count > 0) {
            html += rideCard('All-Time - Runs', d.all_runs, '');
        }

        html += '</div>';
        container.innerHTML = html;
    } catch(e) {
        container.innerHTML = '<div class="error">Error loading stats: ' + e.message + '</div>';
    }
}
window.addEventListener('DOMContentLoaded', loadStats);
</script>
</head><body>
<div class="wrapper">
    <div id="stats-container">
        <div class="loading">Loading Strava stats...</div>
    </div>
</div>
</body></html>"""

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    os.makedirs(CONFIG_DIR, exist_ok=True)

    if not os.path.exists(TOKENS_FILE):
        save_json(TOKENS_FILE, {
            'client_id': '',
            'client_secret': '',
            'access_token': '',
            'refresh_token': '',
            'expires_at': 0,
            'athlete': {}
        })

    if not os.path.exists(WEIGHT_FILE):
        save_json(WEIGHT_FILE, {
            'unit': 'kg',
            'goal_weight': None,
            'entries': []
        })

    if not os.path.exists(SETTINGS_FILE):
        save_json(SETTINGS_FILE, {
            'timezone': 'Asia/Manila',
            'cache_ttl_minutes': 30,
            'calendar_days': 60,
            'weight_unit': 'kg'
        })

    app.run(host='0.0.0.0', port=5062, debug=False)

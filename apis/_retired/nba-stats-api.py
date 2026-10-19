#!/usr/bin/env python3
"""
NBA Stats API Aggregator
========================
Provides NBA game scores, standings, and Yahoo Fantasy league data for Glance dashboard.
Uses the free ESPN API for live data and Yahoo Fantasy API for fantasy league.

Endpoints:
- /games - Today's games with scores
- /standings - NBA standings (East/West)
- /fantasy - Yahoo Fantasy NBA league standings
- /health - Health check

Yahoo Fantasy Setup:
1. Create app at https://developer.yahoo.com/apps/create/
2. Set environment variables: YAHOO_CLIENT_ID, YAHOO_CLIENT_SECRET, YAHOO_LEAGUE_ID
3. On first run, authenticate via browser
"""

import os
import json
import requests
from flask import Flask, jsonify
from flask_cors import CORS
from datetime import datetime
from pathlib import Path
import pytz
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Yahoo Fantasy configuration
YAHOO_CLIENT_ID = os.getenv('YAHOO_CLIENT_ID', '')
YAHOO_CLIENT_SECRET = os.getenv('YAHOO_CLIENT_SECRET', '')
YAHOO_LEAGUE_ID = os.getenv('YAHOO_LEAGUE_ID', '')  # e.g., "418.l.12345"
YAHOO_TOKEN_PATH = os.getenv('YAHOO_TOKEN_PATH', '/data/yahoo_token.json')

# ESPN API endpoints (free, no auth required)
ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
ESPN_STANDINGS = "https://site.api.espn.com/apis/v2/sports/basketball/nba/standings"

# Timezone
TIMEZONE = os.getenv('TIMEZONE', 'Asia/Manila')


def get_team_logo(team_id):
    """Get team logo URL from ESPN CDN"""
    return f"https://a.espncdn.com/i/teamlogos/nba/500/{team_id}.png"


@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "nba-stats-api"})


@app.route('/games')
def get_games():
    """
    Get today's NBA games with scores.
    Returns game status, teams, scores, and broadcast info.
    """
    try:
        response = requests.get(ESPN_SCOREBOARD, timeout=10)
        response.raise_for_status()
        data = response.json()

        games = []
        for event in data.get('events', []):
            competition = event.get('competitions', [{}])[0]
            competitors = competition.get('competitors', [])

            # Get home and away teams
            home_team = None
            away_team = None
            for comp in competitors:
                team_data = {
                    'id': comp.get('team', {}).get('abbreviation', ''),
                    'name': comp.get('team', {}).get('displayName', ''),
                    'shortName': comp.get('team', {}).get('shortDisplayName', ''),
                    'abbreviation': comp.get('team', {}).get('abbreviation', ''),
                    'score': comp.get('score', '0'),
                    'logo': comp.get('team', {}).get('logo', ''),
                    'record': comp.get('records', [{}])[0].get('summary', '') if comp.get('records') else '',
                    'winner': comp.get('winner', False)
                }
                if comp.get('homeAway') == 'home':
                    home_team = team_data
                else:
                    away_team = team_data

            # Game status
            status = event.get('status', {})
            status_type = status.get('type', {})

            # Broadcast info
            broadcasts = competition.get('broadcasts', [])
            broadcast_name = broadcasts[0].get('names', [''])[0] if broadcasts else ''

            # Game time
            game_date = event.get('date', '')

            game = {
                'id': event.get('id', ''),
                'name': event.get('name', ''),
                'shortName': event.get('shortName', ''),
                'date': game_date,
                'homeTeam': home_team,
                'awayTeam': away_team,
                'status': {
                    'state': status_type.get('state', ''),  # pre, in, post
                    'detail': status_type.get('shortDetail', ''),
                    'description': status_type.get('description', ''),
                    'period': status.get('period', 0),
                    'clock': status.get('displayClock', ''),
                    'completed': status_type.get('completed', False)
                },
                'broadcast': broadcast_name,
                'venue': competition.get('venue', {}).get('fullName', '')
            }
            games.append(game)

        # Get current date in configured timezone
        tz = pytz.timezone(TIMEZONE)
        now = datetime.now(tz)

        return jsonify({
            'date': now.strftime('%Y-%m-%d'),
            'dateDisplay': now.strftime('%A, %B %d, %Y'),
            'gamesCount': len(games),
            'games': games
        })

    except requests.RequestException as e:
        return jsonify({'error': str(e), 'games': []}), 500


@app.route('/standings')
def get_standings():
    """
    Get NBA standings for Eastern and Western conferences.
    """
    try:
        response = requests.get(ESPN_STANDINGS, timeout=10)
        response.raise_for_status()
        data = response.json()

        standings = {
            'eastern': [],
            'western': []
        }

        for child in data.get('children', []):
            conf_name = child.get('name', '').lower()
            conf_key = 'eastern' if 'east' in conf_name else 'western'

            for entry in child.get('standings', {}).get('entries', []):
                team = entry.get('team', {})
                stats = {stat.get('name'): stat.get('value') for stat in entry.get('stats', [])}

                team_data = {
                    'rank': int(stats.get('playoffSeed', 0)),
                    'id': team.get('abbreviation', ''),
                    'name': team.get('displayName', ''),
                    'shortName': team.get('shortDisplayName', ''),
                    'abbreviation': team.get('abbreviation', ''),
                    'logo': team.get('logos', [{}])[0].get('href', '') if team.get('logos') else '',
                    'wins': int(stats.get('wins', 0)),
                    'losses': int(stats.get('losses', 0)),
                    'winPercent': float(stats.get('winPercent', 0)),
                    'gamesBehind': float(stats.get('gamesBehind', 0)),
                    'streak': stats.get('streak', ''),
                    'last10': f"{int(stats.get('OTLosses', 0))}-{int(stats.get('OTWins', 0))}" if 'OTLosses' in stats else '',
                    'pointsFor': float(stats.get('pointsFor', 0)),
                    'pointsAgainst': float(stats.get('pointsAgainst', 0)),
                    'differential': float(stats.get('differential', 0))
                }
                standings[conf_key].append(team_data)

        # Sort by rank
        standings['eastern'].sort(key=lambda x: x['rank'])
        standings['western'].sort(key=lambda x: x['rank'])

        return jsonify(standings)

    except requests.RequestException as e:
        return jsonify({'error': str(e), 'eastern': [], 'western': []}), 500


@app.route('/schedule')
def get_schedule():
    """Get upcoming games schedule"""
    try:
        # ESPN scoreboard includes upcoming games
        response = requests.get(ESPN_SCOREBOARD, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Filter for upcoming games (pre state)
        upcoming = []
        for event in data.get('events', []):
            status = event.get('status', {}).get('type', {})
            if status.get('state') == 'pre':
                competition = event.get('competitions', [{}])[0]
                competitors = competition.get('competitors', [])

                home = next((c for c in competitors if c.get('homeAway') == 'home'), {})
                away = next((c for c in competitors if c.get('homeAway') == 'away'), {})

                upcoming.append({
                    'id': event.get('id'),
                    'name': event.get('shortName'),
                    'date': event.get('date'),
                    'time': status.get('shortDetail', ''),
                    'homeTeam': home.get('team', {}).get('abbreviation', ''),
                    'awayTeam': away.get('team', {}).get('abbreviation', ''),
                    'broadcast': competition.get('broadcasts', [{}])[0].get('names', [''])[0] if competition.get('broadcasts') else ''
                })

        return jsonify({'upcoming': upcoming})

    except requests.RequestException as e:
        return jsonify({'error': str(e), 'upcoming': []}), 500


# ============================================
# Yahoo Fantasy NBA League Integration
# ============================================

# Cache for fantasy standings (updated at 2pm daily)
_fantasy_cache = {
    'data': None,
    'last_update': None
}


def get_yahoo_fantasy_standings():
    """
    Fetch Yahoo Fantasy NBA league standings using yfpy library.
    Returns team rankings, wins, losses, and points.
    """
    try:
        from yfpy.query import YahooFantasySportsQuery
        from yfpy.data import Data

        if not all([YAHOO_CLIENT_ID, YAHOO_CLIENT_SECRET, YAHOO_LEAGUE_ID]):
            return {'error': 'Yahoo Fantasy not configured', 'teams': []}

        # Initialize Yahoo Fantasy query
        yahoo_query = YahooFantasySportsQuery(
            league_id=YAHOO_LEAGUE_ID.split('.l.')[-1] if '.l.' in YAHOO_LEAGUE_ID else YAHOO_LEAGUE_ID,
            game_code="nba",
            game_id=418,  # 2024-2025 NBA season
            yahoo_consumer_key=YAHOO_CLIENT_ID,
            yahoo_consumer_secret=YAHOO_CLIENT_SECRET,
            env_var_fallback=False
        )

        # Get league standings
        standings = yahoo_query.get_league_standings()

        teams = []
        for team in standings.teams:
            team_data = {
                'rank': team.team_standings.rank,
                'name': team.name,
                'manager': team.managers[0].nickname if team.managers else 'Unknown',
                'wins': team.team_standings.outcome_totals.wins,
                'losses': team.team_standings.outcome_totals.losses,
                'ties': team.team_standings.outcome_totals.ties,
                'winPct': float(team.team_standings.outcome_totals.percentage),
                'pointsFor': float(team.team_standings.points_for) if hasattr(team.team_standings, 'points_for') else 0,
                'pointsAgainst': float(team.team_standings.points_against) if hasattr(team.team_standings, 'points_against') else 0,
                'streak': team.team_standings.streak.type + str(team.team_standings.streak.value) if hasattr(team.team_standings, 'streak') else '',
                'logo': team.team_logos[0].url if team.team_logos else ''
            }
            teams.append(team_data)

        # Sort by rank
        teams.sort(key=lambda x: x['rank'])

        return {
            'leagueName': standings.name if hasattr(standings, 'name') else 'Fantasy League',
            'teams': teams,
            'lastUpdate': datetime.now().isoformat()
        }

    except ImportError:
        logger.warning("yfpy library not installed. Install with: pip install yfpy")
        return {'error': 'yfpy library not installed', 'teams': []}
    except Exception as e:
        logger.error(f"Yahoo Fantasy API error: {e}")
        return {'error': str(e), 'teams': []}


@app.route('/fantasy')
def get_fantasy():
    """
    Get Yahoo Fantasy NBA league standings.
    Caches data and updates at 2pm daily (configurable via FANTASY_UPDATE_HOUR).
    """
    global _fantasy_cache

    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    update_hour = int(os.getenv('FANTASY_UPDATE_HOUR', '14'))  # Default 2pm

    # Check if we need to update cache
    should_update = False
    if _fantasy_cache['data'] is None:
        should_update = True
    elif _fantasy_cache['last_update']:
        last_update = _fantasy_cache['last_update']
        # Update if it's a new day and past update hour
        if now.date() > last_update.date() and now.hour >= update_hour:
            should_update = True
        # Or if we haven't updated today and it's past update hour
        elif now.date() == last_update.date() and last_update.hour < update_hour and now.hour >= update_hour:
            should_update = True

    if should_update:
        logger.info("Updating Yahoo Fantasy standings cache...")
        _fantasy_cache['data'] = get_yahoo_fantasy_standings()
        _fantasy_cache['last_update'] = now

    if _fantasy_cache['data']:
        return jsonify(_fantasy_cache['data'])
    else:
        return jsonify({'error': 'No fantasy data available', 'teams': []})


@app.route('/fantasy/refresh')
def refresh_fantasy():
    """Force refresh Yahoo Fantasy standings (manual trigger)"""
    global _fantasy_cache
    tz = pytz.timezone(TIMEZONE)
    _fantasy_cache['data'] = get_yahoo_fantasy_standings()
    _fantasy_cache['last_update'] = datetime.now(tz)
    return jsonify(_fantasy_cache['data'])


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5060))
    debug = os.getenv('DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)

from flask import Flask, jsonify
import requests
import os
from datetime import datetime, timedelta
from functools import lru_cache
import time

app = Flask(__name__)

# Configuration from environment
STEAM_API_KEY = os.environ.get('STEAM_API_KEY', '')
STEAM_ID = os.environ.get('STEAM_ID', '')

# Cache settings
CACHE_DURATION = 300  # 5 minutes
cache_data = {}
cache_time = {}

def get_cached(key, fetch_func):
    """Simple time-based cache"""
    now = time.time()
    if key in cache_data and (now - cache_time.get(key, 0)) < CACHE_DURATION:
        return cache_data[key]
    try:
        data = fetch_func()
        cache_data[key] = data
        cache_time[key] = now
        return data
    except Exception as e:
        # Return cached data if available, even if stale
        if key in cache_data:
            return cache_data[key]
        raise e

def fetch_recently_played():
    """Fetch recently played games from Steam API"""
    url = f"https://api.steampowered.com/IPlayerService/GetRecentlyPlayedGames/v1/"
    params = {
        'key': STEAM_API_KEY,
        'steamid': STEAM_ID,
        'count': 10
    }
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    return response.json().get('response', {})

def fetch_owned_games():
    """Fetch owned games with app info for sorting by playtime"""
    url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
    params = {
        'key': STEAM_API_KEY,
        'steamid': STEAM_ID,
        'include_appinfo': 1,
        'include_played_free_games': 1
    }
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    return response.json().get('response', {})

def fetch_player_summary():
    """Fetch player profile info"""
    url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
    params = {
        'key': STEAM_API_KEY,
        'steamids': STEAM_ID
    }
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    players = response.json().get('response', {}).get('players', [])
    return players[0] if players else {}

def fetch_wishlist():
    """Fetch wishlist (public wishlists only)"""
    # Steam wishlist API (works for public wishlists)
    url = f"https://store.steampowered.com/wishlist/profiles/{STEAM_ID}/wishlistdata/"
    params = {'p': 0}
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return {}

def format_playtime(minutes):
    """Format playtime in hours and minutes"""
    hours = minutes // 60
    mins = minutes % 60
    if hours > 0:
        return f"{hours}h {mins}m"
    return f"{mins}m"

def format_last_played(timestamp):
    """Format last played timestamp"""
    if not timestamp:
        return "Unknown"
    dt = datetime.fromtimestamp(timestamp)
    now = datetime.now()
    diff = now - dt

    if diff.days == 0:
        return "Today"
    elif diff.days == 1:
        return "Yesterday"
    elif diff.days < 7:
        return f"{diff.days} days ago"
    elif diff.days < 30:
        weeks = diff.days // 7
        return f"{weeks} week{'s' if weeks > 1 else ''} ago"
    else:
        return dt.strftime("%b %d, %Y")

@app.route('/stats')
def stats():
    """Get Steam profile stats"""
    try:
        # Fetch all data
        recent = get_cached('recent', fetch_recently_played)
        owned = get_cached('owned', fetch_owned_games)
        profile = get_cached('profile', fetch_player_summary)
        wishlist = get_cached('wishlist', fetch_wishlist)

        # Process recently played games (top 3)
        games = []
        for game in recent.get('games', [])[:3]:
            appid = game.get('appid')
            games.append({
                'name': game.get('name', 'Unknown'),
                'appid': appid,
                'thumbnail': f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg",
                'icon': f"https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/{appid}/{game.get('img_icon_url', '')}.jpg",
                'playtime_total': format_playtime(game.get('playtime_forever', 0)),
                'playtime_total_minutes': game.get('playtime_forever', 0),
                'playtime_2weeks': format_playtime(game.get('playtime_2weeks', 0)),
                'playtime_2weeks_minutes': game.get('playtime_2weeks', 0),
                'last_played': format_last_played(game.get('rtime_last_played', 0)),
                'last_played_timestamp': game.get('rtime_last_played', 0)
            })

        # Process top 5 most played games (sorted by total playtime)
        all_games = owned.get('games', [])
        sorted_games = sorted(all_games, key=lambda x: x.get('playtime_forever', 0), reverse=True)
        top_played = []
        for game in sorted_games[:5]:
            appid = game.get('appid')
            playtime_mins = game.get('playtime_forever', 0)
            top_played.append({
                'name': game.get('name', 'Unknown'),
                'appid': appid,
                'thumbnail': f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg",
                'playtime': format_playtime(playtime_mins),
                'playtime_minutes': playtime_mins,
                'playtime_hours': round(playtime_mins / 60, 1)
            })

        # Process wishlist for sales
        wishlist_on_sale = []
        for appid, item in wishlist.items():
            if item.get('subs'):
                for sub in item.get('subs', []):
                    if sub.get('discount_pct', 0) > 0:
                        wishlist_on_sale.append({
                            'name': item.get('name', 'Unknown'),
                            'appid': appid,
                            'thumbnail': f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg",
                            'discount': sub.get('discount_pct', 0),
                            'price': sub.get('price', 0) / 100,  # Convert cents to dollars
                            'original_price': sub.get('price', 0) / 100 / (1 - sub.get('discount_pct', 0) / 100) if sub.get('discount_pct', 0) > 0 else 0
                        })
                        break

        # Sort by discount percentage
        wishlist_on_sale.sort(key=lambda x: x['discount'], reverse=True)

        return jsonify({
            'profile': {
                'name': profile.get('personaname', 'Unknown'),
                'avatar': profile.get('avatarfull', ''),
                'profile_url': profile.get('profileurl', ''),
                'status': 'Online' if profile.get('personastate', 0) == 1 else 'Offline'
            },
            'total_games': owned.get('game_count', 0),
            'recent_games': games,
            'top_played': top_played,
            'wishlist_on_sale': wishlist_on_sale[:5],  # Top 5 sales
            'wishlist_sale_count': len(wishlist_on_sale),
            'total_playtime_2weeks': format_playtime(recent.get('total_count', 0)),
            'cache_updated': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'error': str(e),
            'profile': {'name': 'Error', 'status': 'Unknown'},
            'total_games': 0,
            'recent_games': [],
            'top_played': [],
            'wishlist_on_sale': [],
            'wishlist_sale_count': 0
        }), 500

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "steam_id": STEAM_ID[:4] + "..." if STEAM_ID else "not configured"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5054)

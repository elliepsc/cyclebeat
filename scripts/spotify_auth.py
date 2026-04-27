"""
spotify_auth.py — CycleBeat
Run ONCE locally to generate and cache the Spotify token.
The token is saved to .spotify_cache and mounted into Docker at runtime.

Usage:
    python scripts/spotify_auth.py
"""

import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

load_dotenv()

CACHE_PATH = ".spotify_cache"


def authenticate():
    """Open a browser to authenticate with Spotify and persist the token to disk."""
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
        scope="playlist-read-private user-read-playback-state",
        cache_path=CACHE_PATH,
        open_browser=True
    ))

    user = sp.current_user()
    print(f"\n✅ Authenticated as: {user['display_name']}")
    print(f"   Token saved → {CACHE_PATH}")
    print(f"\n   You can now run: docker-compose up --build")


if __name__ == "__main__":
    authenticate()

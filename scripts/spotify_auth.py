"""
spotify_auth.py — CycleBeat
À lancer UNE FOIS en local pour générer le token Spotify.
Le token est sauvegardé dans .spotify_cache → monté dans Docker.

Usage :
    python scripts/spotify_auth.py
"""

import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

load_dotenv()

CACHE_PATH = ".spotify_cache"

def authenticate():
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
        scope="playlist-read-private user-read-playback-state",
        cache_path=CACHE_PATH,
        open_browser=True
    ))

    # Force l'authentification
    user = sp.current_user()
    print(f"\n✅ Authentifié en tant que : {user['display_name']}")
    print(f"   Token sauvegardé → {CACHE_PATH}")
    print(f"\n   Tu peux maintenant lancer docker-compose up --build")

if __name__ == "__main__":
    authenticate()

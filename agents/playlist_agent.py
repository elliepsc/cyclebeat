"""
Playlist Agent — CycleBeat
Récupère les tracks Spotify + audio analysis via token caché (pas de browser dans Docker).
"""

import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
from typing import List

load_dotenv()

CACHE_PATH = os.getenv("SPOTIFY_CACHE_PATH", ".spotify_cache")


def get_spotify_client() -> spotipy.Spotify:
    """
    Utilise le token caché généré par scripts/spotify_auth.py.
    Pas de browser requis → fonctionne dans Docker.
    """
    return spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
        scope="playlist-read-private user-read-playback-state",
        cache_path=CACHE_PATH,
        open_browser=False  # ← pas de browser en Docker
    ))


def extract_playlist_id(playlist_url: str) -> str:
    return playlist_url.split("/playlist/")[-1].split("?")[0]


def fetch_tracks(sp: spotipy.Spotify, playlist_id: str) -> List[dict]:
    results = sp.playlist_tracks(playlist_id)
    tracks_data = []

    for item in results["items"]:
        track = item["track"]
        if not track:
            continue

        track_id = track["id"]
        duration_ms = track["duration_ms"]

        try:
            analysis = sp.audio_analysis(track_id)
            sections = [
                {
                    "start_s": round(s["start"], 1),
                    "duration_s": round(s["duration"], 1),
                    "loudness": round(s["loudness"], 2),
                    "tempo": round(s["tempo"], 1),
                }
                for s in analysis["sections"]
            ]
        except Exception:
            # Fallback : une seule section sur tout le morceau
            sections = [{
                "start_s": 0.0,
                "duration_s": round(duration_ms / 1000, 1),
                "loudness": -8.0,
                "tempo": 128.0,
            }]

        tracks_data.append({
            "track_id": track_id,
            "track_name": track["name"],
            "artist": track["artists"][0]["name"],
            "duration_s": round(duration_ms / 1000, 1),
            "sections": sections,
        })

    return tracks_data


def run_playlist_agent(playlist_url: str) -> dict:
    sp = get_spotify_client()
    playlist_id = extract_playlist_id(playlist_url)
    playlist_info = sp.playlist(playlist_id)
    tracks = fetch_tracks(sp, playlist_id)

    # Timestamps absolus dans la session
    cursor = 0.0
    for track in tracks:
        track["session_start_s"] = cursor
        cursor += track["duration_s"]

    return {
        "playlist_name": playlist_info["name"],
        "total_duration_s": cursor,
        "tracks": tracks,
    }


if __name__ == "__main__":
    url = input("URL playlist Spotify : ")
    result = run_playlist_agent(url)
    print(f"\n✅ {result['playlist_name']} — {len(result['tracks'])} tracks")

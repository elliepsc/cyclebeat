"""
Playlist Agent — CycleBeat
Fetches Spotify tracks and audio analysis using a cached token (no browser needed inside Docker).
"""

import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
from typing import List

load_dotenv()

CACHE_PATH = os.getenv("SPOTIFY_CACHE_PATH", ".spotify_cache")


def get_spotify_client() -> spotipy.Spotify:
    """Return an authenticated Spotify client using a pre-cached token (no browser required)."""
    return spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
        scope="playlist-read-private user-read-playback-state",
        cache_path=CACHE_PATH,
        open_browser=False  # no browser needed inside Docker
    ))


def extract_playlist_id(playlist_url: str) -> str:
    """Extract the Spotify playlist ID from a full playlist URL."""
    return playlist_url.split("/playlist/")[-1].split("?")[0]


def fetch_tracks(sp: spotipy.Spotify, playlist_id: str) -> List[dict]:
    """Fetch all tracks from a playlist and their Spotify audio analysis sections."""
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
            # Fallback: single section covering the full track
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
    """Fetch all tracks and compute absolute session timestamps for each track."""
    sp = get_spotify_client()
    playlist_id = extract_playlist_id(playlist_url)
    playlist_info = sp.playlist(playlist_id)
    tracks = fetch_tracks(sp, playlist_id)

    # Compute absolute start timestamps within the session
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
    url = input("Spotify playlist URL: ")
    result = run_playlist_agent(url)
    print(f"\n✅ {result['playlist_name']} — {len(result['tracks'])} tracks")

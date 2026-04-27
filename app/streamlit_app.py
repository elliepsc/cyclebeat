"""
CycleBeat — Streamlit App
Interface live de coaching cycling synchronisée sur la musique.
"""

import json
import time
import os
import streamlit as st
from datetime import datetime

# ─── CONFIG ──────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="CycleBeat 🚴",
    page_icon="🚴",
    layout="centered"
)

DEMO_PATH = os.path.join(os.path.dirname(__file__), "../data/demo_session.json")
GENERATED_PATH = os.path.join(os.path.dirname(__file__), "../data/generated_session.json")
FEEDBACK_PATH = os.path.join(os.path.dirname(__file__), "../data/feedback.json")


# ─── UTILS ───────────────────────────────────────────────────────────────────

def load_session(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_current_cue(session: dict, elapsed_s: float) -> dict | None:
    """Retourne le cue actif pour un timestamp donné."""
    for track in session["tracks"]:
        for cue in track["cues"]:
            end_s = cue["start_s"] + cue["duration_s"]
            if cue["start_s"] <= elapsed_s < end_s:
                return cue, track
    return None, None


def get_next_cue(session: dict, elapsed_s: float) -> dict | None:
    """Retourne le prochain cue."""
    all_cues = []
    for track in session["tracks"]:
        for cue in track["cues"]:
            all_cues.append((cue, track))
    all_cues.sort(key=lambda x: x[0]["start_s"])

    for cue, track in all_cues:
        if cue["start_s"] > elapsed_s:
            return cue, track
    return None, None


def format_time(seconds: float) -> str:
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m:02d}:{s:02d}"


def save_feedback(session_title: str, rating: str, note: str):
    feedback = []
    if os.path.exists(FEEDBACK_PATH):
        with open(FEEDBACK_PATH) as f:
            feedback = json.load(f)
    feedback.append({
        "timestamp": datetime.now().isoformat(),
        "session": session_title,
        "rating": rating,
        "note": note
    })
    with open(FEEDBACK_PATH, "w") as f:
        json.dump(feedback, f, ensure_ascii=False, indent=2)


def load_feedback() -> list:
    if not os.path.exists(FEEDBACK_PATH):
        return []
    with open(FEEDBACK_PATH) as f:
        return json.load(f)


# ─── SIDEBAR ─────────────────────────────────────────────────────────────────

st.sidebar.title("🚴 CycleBeat")
mode = st.sidebar.radio(
    "Mode",
    ["🎵 Demo (sans Spotify)", "🔗 Spotify", "📊 Monitoring"]
)

# ─── MODE DEMO ───────────────────────────────────────────────────────────────

if mode == "🎵 Demo (sans Spotify)":
    st.title("🚴 CycleBeat — Demo Ride")
    st.caption("Séance pré-générée — aucun compte requis")

    session = load_session(DEMO_PATH)
    total = session["session"]["total_duration_s"]

    col1, col2 = st.columns(2)
    col1.metric("Durée totale", f"{total/60:.0f} min")
    col2.metric("Morceaux", len(session["tracks"]))

    st.divider()

    if "running" not in st.session_state:
        st.session_state.running = False
    if "start_time" not in st.session_state:
        st.session_state.start_time = None
    if "elapsed" not in st.session_state:
        st.session_state.elapsed = 0.0

    col_start, col_stop, col_reset = st.columns(3)
    if col_start.button("▶️ Démarrer", disabled=st.session_state.running):
        st.session_state.running = True
        st.session_state.start_time = time.time() - st.session_state.elapsed

    if col_stop.button("⏸️ Pause", disabled=not st.session_state.running):
        st.session_state.running = False
        st.session_state.elapsed = time.time() - st.session_state.start_time

    if col_reset.button("🔄 Reset"):
        st.session_state.running = False
        st.session_state.start_time = None
        st.session_state.elapsed = 0.0

    # Affichage live
    if st.session_state.running:
        st.session_state.elapsed = time.time() - st.session_state.start_time

    elapsed = st.session_state.elapsed
    progress = min(elapsed / total, 1.0)

    st.progress(progress, text=f"⏱️ {format_time(elapsed)} / {format_time(total)}")

    # Cue actuel + prochain
    current_cue, current_track = get_current_cue(session, elapsed)
    next_cue, next_track = get_next_cue(session, elapsed)

    # ⚠️ Alerte pré-changement (10 secondes avant)
    ALERT_THRESHOLD = 10
    if current_cue and next_cue:
        time_to_next = next_cue["start_s"] - elapsed
        if 0 < time_to_next <= ALERT_THRESHOLD:
            st.warning(
                f"⚠️ **Changement dans {time_to_next:.0f}s** — "
                f"Prépare-toi : {next_cue['emoji']} {next_cue['phase'].replace('_', ' ').title()} "
                f"— Résistance {next_cue['resistance']}"
            )

    if current_cue:
        remaining = current_cue["start_s"] + current_cue["duration_s"] - elapsed

        # Instruction principale — grande et lisible sur le vélo
        st.markdown(f"""
        <div style='
            background: linear-gradient(135deg, #1a1a2e, #16213e);
            border-radius: 16px;
            padding: 32px;
            text-align: center;
            margin: 16px 0;
        '>
            <div style='font-size: 64px; margin-bottom: 8px'>{current_cue['emoji']}</div>
            <div style='font-size: 28px; font-weight: bold; color: white; margin-bottom: 12px'>
                {current_cue['instruction']}
            </div>
            <div style='font-size: 20px; color: #888; margin-bottom: 8px'>
                Résistance : {'🟥' * current_cue['resistance']}{'⬜' * (10 - current_cue['resistance'])}
                <strong style='color: white'> {current_cue['resistance']}/10</strong>
            </div>
            <div style='font-size: 16px; color: #aaa'>
                ⏳ {format_time(remaining)} restantes
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.caption(f"🎵 {current_track['track_name']} — {current_track['artist']} | {current_cue['bpm']:.0f} BPM")

    else:
        st.info("Lance la séance pour voir les instructions de coaching.")

    # Prochain cue
    if next_cue:
        st.markdown(f"**Prochaine phase :** {next_cue['emoji']} {next_cue['phase'].replace('_', ' ').title()} — dans {format_time(next_cue['start_s'] - elapsed)}")

    # Auto-refresh
    if st.session_state.running:
        time.sleep(1)
        st.rerun()

    st.divider()

    # Feedback
    st.subheader("💬 Feedback de séance")
    rating = st.radio("Comment était cette séance ?", ["👍 Super", "😐 Correct", "👎 Difficile"], horizontal=True)
    note = st.text_input("Une note ? (optionnel)")
    if st.button("Envoyer le feedback"):
        save_feedback(session["session"]["title"], rating, note)
        st.success("Merci ! Feedback enregistré.")


# ─── MODE SPOTIFY ────────────────────────────────────────────────────────────

elif mode == "🔗 Spotify":
    st.title("🎵 CycleBeat — Génère ta séance")

    playlist_url = st.text_input(
        "URL de ta playlist Spotify",
        placeholder="https://open.spotify.com/playlist/..."
    )
    use_llm = st.checkbox("Coaching personnalisé (LLM)", value=True)

    if st.button("🚀 Générer la séance") and playlist_url:
        with st.spinner("Analyse de ta playlist en cours..."):
            try:
                from agents.orchestrator import generate_session
                session = generate_session(playlist_url, use_llm=use_llm)
                st.success(f"✅ Séance générée : {session['session']['title']}")
                st.info("Recharge la page et passe en mode Demo pour lancer la séance.")
            except Exception as e:
                st.error(f"Erreur : {e}")
                st.info("💡 Si tu n'as pas de compte Spotify configuré, utilise le mode Demo.")


# ─── MODE MONITORING ─────────────────────────────────────────────────────────

elif mode == "📊 Monitoring":
    st.title("📊 CycleBeat — Dashboard")

    feedback = load_feedback()

    if not feedback:
        st.info("Aucun feedback encore. Lance une séance et donne ton avis !")
    else:
        import pandas as pd

        df = pd.DataFrame(feedback)
        df["date"] = pd.to_datetime(df["timestamp"]).dt.date

        # KPIs
        col1, col2, col3 = st.columns(3)
        col1.metric("Séances totales", len(df))
        col2.metric("👍 Satisfaction", f"{(df['rating'].str.contains('Super').sum() / len(df) * 100):.0f}%")
        col3.metric("Sessions cette semaine", len(df[df["date"] >= (pd.Timestamp.now() - pd.Timedelta(days=7)).date()]))

        st.divider()

        # Chart 1 — Séances par jour
        st.subheader("📈 Séances par jour")
        sessions_by_day = df.groupby("date").size().reset_index(name="count")
        st.bar_chart(sessions_by_day.set_index("date"))

        # Chart 2 — Répartition des ratings
        st.subheader("⭐ Répartition des feedbacks")
        rating_counts = df["rating"].value_counts().reset_index()
        rating_counts.columns = ["Rating", "Count"]
        st.bar_chart(rating_counts.set_index("Rating"))

        # Chart 3 — Séances par playlist
        st.subheader("🎵 Séances par playlist")
        session_counts = df["session"].value_counts().reset_index()
        session_counts.columns = ["Playlist", "Count"]
        st.bar_chart(session_counts.set_index("Playlist"))

        # Chart 4 — Feedbacks négatifs dans le temps
        st.subheader("👎 Feedbacks difficiles dans le temps")
        df["is_negative"] = df["rating"].str.contains("Difficile")
        neg_by_day = df.groupby("date")["is_negative"].sum().reset_index()
        st.line_chart(neg_by_day.set_index("date"))

        # Chart 5 — Tableau des notes textuelles
        st.subheader("📝 Notes utilisateurs")
        notes = df[df["note"].notna() & (df["note"] != "")][["date", "rating", "note"]]
        if not notes.empty:
            st.dataframe(notes, use_container_width=True)
        else:
            st.caption("Aucune note textuelle encore.")

"""
CycleBeat — Streamlit App
Live cycling coaching interface synchronized to the music session timeline.
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
    """Load a session JSON file from disk."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_current_cue(session: dict, elapsed_s: float):
    """Return the active cue and its track for the given elapsed time."""
    for track in session["tracks"]:
        for cue in track["cues"]:
            end_s = cue["start_s"] + cue["duration_s"]
            if cue["start_s"] <= elapsed_s < end_s:
                return cue, track
    return None, None


def get_next_cue(session: dict, elapsed_s: float):
    """Return the next upcoming cue after the given elapsed time."""
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
    """Format a duration in seconds as MM:SS."""
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m:02d}:{s:02d}"


def save_feedback(session_title: str, rating: str, note: str):
    """Append a feedback entry to the feedback JSON log."""
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
    """Load all collected feedback entries from disk."""
    if not os.path.exists(FEEDBACK_PATH):
        return []
    with open(FEEDBACK_PATH) as f:
        return json.load(f)


# ─── SIDEBAR ─────────────────────────────────────────────────────────────────

st.sidebar.title("🚴 CycleBeat")

_generated_exists = os.path.exists(GENERATED_PATH)
_mode_options = ["🎵 Demo (no Spotify needed)", "🔗 Spotify"]
if _generated_exists:
    _mode_options.insert(1, "🎯 Generated Session")

mode = st.sidebar.radio("Mode", _mode_options)

st.sidebar.divider()
st.sidebar.markdown(
    "📊 **Monitoring dashboard**  \n[→ open on port 8050](http://localhost:8050)",
    unsafe_allow_html=False,
)

# ─── DEMO MODE ───────────────────────────────────────────────────────────────

if mode == "🎵 Demo (no Spotify needed)":
    st.title("🚴 CycleBeat — Demo Ride")
    st.caption("Pre-generated session — no account required")

    session = load_session(DEMO_PATH)
    total = session["session"]["total_duration_s"]

    col1, col2 = st.columns(2)
    col1.metric("Total duration", f"{total/60:.0f} min")
    col2.metric("Tracks", len(session["tracks"]))

    st.divider()

    if "running" not in st.session_state:
        st.session_state.running = False
    if "start_time" not in st.session_state:
        st.session_state.start_time = None
    if "elapsed" not in st.session_state:
        st.session_state.elapsed = 0.0

    col_start, col_stop, col_reset = st.columns(3)
    if col_start.button("▶️ Start", disabled=st.session_state.running):
        st.session_state.running = True
        st.session_state.start_time = time.time() - st.session_state.elapsed

    if col_stop.button("⏸️ Pause", disabled=not st.session_state.running):
        st.session_state.running = False
        st.session_state.elapsed = time.time() - st.session_state.start_time

    if col_reset.button("🔄 Reset"):
        st.session_state.running = False
        st.session_state.start_time = None
        st.session_state.elapsed = 0.0

    if st.session_state.running:
        st.session_state.elapsed = time.time() - st.session_state.start_time

    elapsed = st.session_state.elapsed
    progress = min(elapsed / total, 1.0)

    st.progress(progress, text=f"⏱️ {format_time(elapsed)} / {format_time(total)}")

    current_cue, current_track = get_current_cue(session, elapsed)
    next_cue, next_track = get_next_cue(session, elapsed)

    # Pre-change alert 10 seconds ahead
    ALERT_THRESHOLD = 10
    if current_cue and next_cue:
        time_to_next = next_cue["start_s"] - elapsed
        if 0 < time_to_next <= ALERT_THRESHOLD:
            st.warning(
                f"⚠️ **Change in {time_to_next:.0f}s** — "
                f"Get ready: {next_cue['emoji']} {next_cue['phase'].replace('_', ' ').title()} "
                f"— Resistance {next_cue['resistance']}"
            )

    if current_cue:
        remaining = current_cue["start_s"] + current_cue["duration_s"] - elapsed
        res = current_cue['resistance']
        res_bar = '🟥' * res + '⬜' * (10 - res)

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
                Resistance: {res_bar}
                <strong style='color: white'> {res}/10</strong>
            </div>
            <div style='font-size: 16px; color: #aaa'>
                ⏳ {format_time(remaining)} remaining
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.caption(
            f"🎵 {current_track['track_name']} — {current_track['artist']}"
            f" | {current_cue['bpm']:.0f} BPM"
        )

    else:
        st.info("Start the session to see live coaching instructions.")

    if next_cue:
        phase_label = next_cue['phase'].replace('_', ' ').title()
        st.markdown(
            f"**Next phase:** {next_cue['emoji']} {phase_label}"
            f" — in {format_time(next_cue['start_s'] - elapsed)}"
        )

    # Auto-refresh every second while running
    if st.session_state.running:
        time.sleep(1)
        st.rerun()

    st.divider()

    # Session feedback
    st.subheader("💬 Session Feedback")
    rating = st.radio("How was this session?", ["👍 Great", "😐 Okay", "👎 Hard"], horizontal=True)
    note = st.text_input("Any notes? (optional)")
    if st.button("Submit feedback"):
        save_feedback(session["session"]["title"], rating, note)
        st.success("Thanks! Feedback saved.")


# ─── GENERATED SESSION MODE ──────────────────────────────────────────────────

elif mode == "🎯 Generated Session":
    st.title("🎯 CycleBeat — Your Generated Ride")
    st.caption("Session generated from your Spotify playlist")

    session = load_session(GENERATED_PATH)
    total = session["session"]["total_duration_s"]

    col1, col2 = st.columns(2)
    col1.metric("Total duration", f"{total/60:.0f} min")
    col2.metric("Tracks", len(session["tracks"]))

    st.divider()

    if "running" not in st.session_state:
        st.session_state.running = False
    if "start_time" not in st.session_state:
        st.session_state.start_time = None
    if "elapsed" not in st.session_state:
        st.session_state.elapsed = 0.0

    col_start, col_stop, col_reset = st.columns(3)
    if col_start.button("▶️ Start", disabled=st.session_state.running):
        st.session_state.running = True
        st.session_state.start_time = time.time() - st.session_state.elapsed

    if col_stop.button("⏸️ Pause", disabled=not st.session_state.running):
        st.session_state.running = False
        st.session_state.elapsed = time.time() - st.session_state.start_time

    if col_reset.button("🔄 Reset"):
        st.session_state.running = False
        st.session_state.start_time = None
        st.session_state.elapsed = 0.0

    if st.session_state.running:
        st.session_state.elapsed = time.time() - st.session_state.start_time

    elapsed = st.session_state.elapsed
    progress = min(elapsed / total, 1.0)

    st.progress(progress, text=f"⏱️ {format_time(elapsed)} / {format_time(total)}")

    current_cue, current_track = get_current_cue(session, elapsed)
    next_cue, next_track = get_next_cue(session, elapsed)

    ALERT_THRESHOLD = 10
    if current_cue and next_cue:
        time_to_next = next_cue["start_s"] - elapsed
        if 0 < time_to_next <= ALERT_THRESHOLD:
            st.warning(
                f"⚠️ **Change in {time_to_next:.0f}s** — "
                f"Get ready: {next_cue['emoji']} "
                f"{next_cue['phase'].replace('_', ' ').title()} "
                f"— Resistance {next_cue['resistance']}"
            )

    if current_cue:
        remaining = current_cue["start_s"] + current_cue["duration_s"] - elapsed
        res = current_cue['resistance']
        res_bar = '🟥' * res + '⬜' * (10 - res)
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
                Resistance: {res_bar}
                <strong style='color: white'> {res}/10</strong>
            </div>
            <div style='font-size: 16px; color: #aaa'>
                ⏳ {format_time(remaining)} remaining
            </div>
        </div>
        """, unsafe_allow_html=True)
        st.caption(
            f"🎵 {current_track['track_name']} — {current_track['artist']}"
            f" | {current_cue['bpm']:.0f} BPM"
        )
    else:
        st.info("Start the session to see live coaching instructions.")

    if next_cue:
        st.markdown(
            f"**Next phase:** {next_cue['emoji']} "
            f"{next_cue['phase'].replace('_', ' ').title()} "
            f"— in {format_time(next_cue['start_s'] - elapsed)}"
        )

    if st.session_state.running:
        time.sleep(1)
        st.rerun()

    st.divider()
    st.subheader("💬 Session Feedback")
    rating = st.radio(
        "How was this session?", ["👍 Great", "😐 Okay", "👎 Hard"],
        horizontal=True
    )
    note = st.text_input("Any notes? (optional)")
    if st.button("Submit feedback"):
        save_feedback(session["session"]["title"], rating, note)
        st.success("Thanks! Feedback saved.")


# ─── SPOTIFY MODE ────────────────────────────────────────────────────────────

elif mode == "🔗 Spotify":
    st.title("🎵 CycleBeat — Generate Your Session")

    playlist_url = st.text_input(
        "Your Spotify playlist URL",
        placeholder="https://open.spotify.com/playlist/..."
    )
    use_llm = st.checkbox("Personalised coaching (LLM)", value=True)
    use_hybrid = st.checkbox("Hybrid search (vector + keyword)", value=True)

    if st.button("🚀 Generate session") and playlist_url:
        with st.spinner("Analysing your playlist..."):
            try:
                from agents.orchestrator import generate_session
                session = generate_session(playlist_url, use_llm=use_llm, use_hybrid=use_hybrid)
                st.success(
                    f"✅ Session generated: {session['session']['title']}"
                )
                st.info(
                    "Reload the page — a **Generated Session** mode "
                    "will appear in the sidebar to start your ride."
                )
            except Exception as e:
                st.error(f"Error: {e}")
                st.info("💡 No Spotify account configured? Use Demo mode.")


"""
CycleBeat — Dash Coaching App (port 8501)

Replaces Streamlit for the coaching UI. Three tabs:
  • Demo       — pre-generated session, no Spotify needed
  • Your ride  — generated from your Spotify playlist
  • Generate   — submit a Spotify URL to build a new session

Real-time timer uses dcc.Interval (1 s) + dcc.Store instead of
Streamlit's time.sleep + st.rerun() polling.
"""

import json
import os
import sys
import time
from pathlib import Path

import dash
from dash import Input, Output, State, dcc, html, callback_context
import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).parent.parent))

_DATA = Path(__file__).parent.parent / "data"
_DEMO_PATH = _DATA / "demo_session.json"
_GEN_PATH = _DATA / "generated_session.json"

# ── Palette ───────────────────────────────────────────────────────────────────
_BG = "#0f0f1a"
_CARD = "#1a1a2e"
_CARD2 = "#16213e"
_ACCENT = "#4f6ef7"
_RED = "#ef4444"
_GREEN = "#22c55e"
_MUTED = "#666688"
_TEXT = "#e0e0e0"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _load(path: Path) -> dict | None:
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def _fmt(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def _all_cues(session: dict) -> list[dict]:
    cues = []
    for track in session.get("tracks", []):
        for cue in track.get("cues", []):
            cues.append({**cue, "_track": track})
    return sorted(cues, key=lambda c: c["start_s"])


def _current_cue(cues: list, elapsed: float) -> dict | None:
    for c in cues:
        if c["start_s"] <= elapsed < c["start_s"] + c["duration_s"]:
            return c
    return None


def _next_cue(cues: list, elapsed: float) -> dict | None:
    for c in cues:
        if c["start_s"] > elapsed:
            return c
    return None


def _res_bar(resistance: int) -> str:
    return "🟥" * resistance + "⬜" * (10 - resistance)


# ── Shared layout pieces ──────────────────────────────────────────────────────

def _cue_card(cue: dict, elapsed: float) -> html.Div:
    remaining = cue["start_s"] + cue["duration_s"] - elapsed
    res = cue.get("resistance", 5)
    return html.Div(
        [
            html.Div(cue.get("emoji", "🚴"), style={"fontSize": "60px"}),
            html.Div(
                cue.get("instruction", ""),
                style={
                    "fontSize": "1.5rem",
                    "fontWeight": "700",
                    "color": "white",
                    "margin": "12px 0",
                },
            ),
            html.Div(
                f"Resistance: {_res_bar(res)}  {res}/10",
                style={"fontSize": "1.1rem", "color": _MUTED, "letterSpacing": "2px"},
            ),
            html.Div(
                f"⏳ {_fmt(remaining)} remaining",
                style={"fontSize": "0.95rem", "color": _MUTED, "marginTop": "8px"},
            ),
        ],
        style={
            "background": f"linear-gradient(135deg, {_CARD}, {_CARD2})",
            "borderRadius": "16px",
            "padding": "32px",
            "textAlign": "center",
            "margin": "16px 0",
        },
    )


def _timer_controls(tab_id: str) -> html.Div:
    return html.Div(
        [
            html.Button(
                "▶ Start",
                id=f"btn-start-{tab_id}",
                n_clicks=0,
                style=_btn_style(_ACCENT),
            ),
            html.Button(
                "⏸ Pause",
                id=f"btn-pause-{tab_id}",
                n_clicks=0,
                style=_btn_style(_MUTED),
            ),
            html.Button(
                "↺ Reset",
                id=f"btn-reset-{tab_id}",
                n_clicks=0,
                style=_btn_style(_RED),
            ),
        ],
        style={"display": "flex", "gap": "12px", "marginBottom": "16px"},
    )


def _btn_style(color: str) -> dict:
    return {
        "background": color,
        "color": "white",
        "border": "none",
        "borderRadius": "8px",
        "padding": "10px 22px",
        "fontSize": "1rem",
        "cursor": "pointer",
        "fontWeight": "600",
    }


def _feedback_block(tab_id: str) -> html.Div:
    return html.Div(
        [
            html.Hr(style={"borderColor": _CARD, "margin": "24px 0"}),
            html.H3("Session feedback", style={"color": _TEXT}),
            dcc.RadioItems(
                id=f"rating-{tab_id}",
                options=[
                    {"label": " 👍 Great", "value": "👍 Great"},
                    {"label": " 😐 Okay",  "value": "😐 Okay"},
                    {"label": " 👎 Hard",  "value": "👎 Hard"},
                ],
                value="👍 Great",
                inline=True,
                style={"color": _TEXT, "marginBottom": "12px"},
            ),
            dcc.Input(
                id=f"note-{tab_id}",
                placeholder="Any notes? (optional)",
                type="text",
                style={
                    "width": "100%",
                    "background": _CARD,
                    "color": _TEXT,
                    "border": f"1px solid {_MUTED}",
                    "borderRadius": "8px",
                    "padding": "10px",
                    "marginBottom": "12px",
                    "boxSizing": "border-box",
                },
            ),
            html.Button(
                "Submit feedback",
                id=f"btn-feedback-{tab_id}",
                n_clicks=0,
                style=_btn_style(_GREEN),
            ),
            html.Div(id=f"feedback-msg-{tab_id}", style={"marginTop": "8px", "color": _GREEN}),
        ]
    )


# ── App ───────────────────────────────────────────────────────────────────────

app = dash.Dash(
    __name__,
    title="CycleBeat 🚴",
    suppress_callback_exceptions=True,
)

_TABS_STYLE = {"backgroundColor": _BG, "borderBottom": f"2px solid {_CARD}"}
_TAB_STYLE = {
    "backgroundColor": _BG,
    "color": _MUTED,
    "border": "none",
    "padding": "14px 24px",
}
_TAB_SELECTED = {**_TAB_STYLE, "color": _ACCENT, "borderBottom": f"2px solid {_ACCENT}"}

_gen_exists = _GEN_PATH.exists()

_tabs = [
    dcc.Tab(label="🎵 Demo", value="demo", style=_TAB_STYLE, selected_style=_TAB_SELECTED),
    dcc.Tab(label="🔗 Generate", value="generate", style=_TAB_STYLE, selected_style=_TAB_SELECTED),
]
if _gen_exists:
    _tabs.insert(1, dcc.Tab(
        label="🎯 Your ride", value="ride",
        style=_TAB_STYLE, selected_style=_TAB_SELECTED,
    ))

_header = html.Div(
    [
        html.Span("🚴 CycleBeat", style={"fontSize": "1.8rem", "fontWeight": "700", "color": _ACCENT}),
        html.A(
            "📊 Dashboard →",
            href="http://localhost:8050",
            target="_blank",
            style={"color": _MUTED, "fontSize": "0.9rem", "marginLeft": "24px"},
        ),
    ],
    style={"padding": "20px 32px 0", "display": "flex", "alignItems": "baseline"},
)

app.layout = html.Div(
    [
        _header,
        dcc.Tabs(
            id="tabs",
            value="demo",
            children=_tabs,
            style=_TABS_STYLE,
        ),
        html.Div(id="tab-content"),

        # Shared timer stores and intervals for demo / ride tabs
        dcc.Store(id="state-demo", data={"running": False, "start_ts": None, "elapsed": 0.0}),
        dcc.Store(id="state-ride", data={"running": False, "start_ts": None, "elapsed": 0.0}),
        dcc.Interval(id="tick-demo", interval=1000, disabled=True),
        dcc.Interval(id="tick-ride", interval=1000, disabled=True),
    ],
    style={
        "backgroundColor": _BG,
        "minHeight": "100vh",
        "fontFamily": "system-ui, -apple-system, sans-serif",
        "color": _TEXT,
    },
)


# ── Tab content ───────────────────────────────────────────────────────────────

def _coaching_tab(tab_id: str, session: dict) -> html.Div:
    total = session["session"]["total_duration_s"]
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(f"⏱ {_fmt(total)}", style={"color": _MUTED}),
                            html.Span(" · ", style={"color": _MUTED}),
                            html.Span(
                                f"{len(session['tracks'])} tracks",
                                style={"color": _MUTED},
                            ),
                        ],
                        style={"marginBottom": "16px", "fontSize": "0.9rem"},
                    ),
                    _timer_controls(tab_id),
                    html.Div(id=f"progress-{tab_id}"),
                    html.Div(id=f"alert-{tab_id}"),
                    html.Div(id=f"cue-{tab_id}"),
                    html.Div(id=f"next-{tab_id}"),
                ],
                style={"padding": "24px 32px"},
            ),
            _feedback_block(tab_id),
        ]
    )


@app.callback(Output("tab-content", "children"), Input("tabs", "value"))
def render_tab(tab):
    if tab == "demo":
        s = _load(_DEMO_PATH)
        if s is None:
            return html.Div("Demo session not found.", style={"padding": "32px", "color": _RED})
        return _coaching_tab("demo", s)

    if tab == "ride":
        s = _load(_GEN_PATH)
        if s is None:
            return html.Div("No generated session yet.", style={"padding": "32px", "color": _RED})
        return _coaching_tab("ride", s)

    if tab == "generate":
        return html.Div(
            [
                html.H3("Generate your session", style={"color": _TEXT}),
                dcc.Input(
                    id="playlist-url",
                    placeholder="https://open.spotify.com/playlist/...",
                    type="text",
                    style={
                        "width": "100%",
                        "background": _CARD,
                        "color": _TEXT,
                        "border": f"1px solid {_MUTED}",
                        "borderRadius": "8px",
                        "padding": "12px",
                        "marginBottom": "12px",
                        "boxSizing": "border-box",
                    },
                ),
                dcc.Checklist(
                    id="gen-options",
                    options=[
                        {"label": "  Personalised coaching (LLM)", "value": "llm"},
                        {"label": "  Hybrid search",               "value": "hybrid"},
                    ],
                    value=["llm", "hybrid"],
                    style={"color": _TEXT, "marginBottom": "16px"},
                ),
                html.Button(
                    "🚀 Generate session",
                    id="btn-generate",
                    n_clicks=0,
                    style=_btn_style(_ACCENT),
                ),
                html.Div(id="gen-status", style={"marginTop": "16px", "color": _TEXT}),
            ],
            style={"padding": "24px 32px"},
        )
    return html.Div()


# ── Timer state machine (demo) ────────────────────────────────────────────────

@app.callback(
    Output("state-demo", "data"),
    Output("tick-demo", "disabled"),
    Input("btn-start-demo", "n_clicks"),
    Input("btn-pause-demo", "n_clicks"),
    Input("btn-reset-demo", "n_clicks"),
    Input("tick-demo", "n_intervals"),
    State("state-demo", "data"),
    prevent_initial_call=True,
)
def timer_demo(n_start, n_pause, n_reset, _tick, state):
    return _tick_state(state, callback_context.triggered_id)


@app.callback(
    Output("state-ride", "data"),
    Output("tick-ride", "disabled"),
    Input("btn-start-ride", "n_clicks"),
    Input("btn-pause-ride", "n_clicks"),
    Input("btn-reset-ride", "n_clicks"),
    Input("tick-ride", "n_intervals"),
    State("state-ride", "data"),
    prevent_initial_call=True,
)
def timer_ride(n_start, n_pause, n_reset, _tick, state):
    return _tick_state(state, callback_context.triggered_id)


def _tick_state(state: dict, triggered: str) -> tuple[dict, bool]:
    now = time.time()
    if triggered and "reset" in triggered:
        return {"running": False, "start_ts": None, "elapsed": 0.0}, True
    if triggered and "start" in triggered:
        elapsed = state.get("elapsed", 0.0)
        return {"running": True, "start_ts": now - elapsed, "elapsed": elapsed}, False
    if triggered and "pause" in triggered:
        elapsed = now - state["start_ts"] if state.get("start_ts") else state.get("elapsed", 0.0)
        return {"running": False, "start_ts": None, "elapsed": elapsed}, True
    # tick
    if state.get("running") and state.get("start_ts"):
        elapsed = now - state["start_ts"]
        return {**state, "elapsed": elapsed}, False
    return state, not state.get("running", False)


# ── Display callbacks (demo) ──────────────────────────────────────────────────

def _make_display_callback(tab_id: str, path: Path):
    @app.callback(
        Output(f"progress-{tab_id}", "children"),
        Output(f"alert-{tab_id}", "children"),
        Output(f"cue-{tab_id}", "children"),
        Output(f"next-{tab_id}", "children"),
        Input(f"state-{tab_id}", "data"),
    )
    def display(state):
        session = _load(path)
        if session is None:
            return None, None, None, None

        elapsed = state.get("elapsed", 0.0)
        total = session["session"]["total_duration_s"]
        pct = min(elapsed / total, 1.0) * 100

        # Progress bar
        progress = html.Div(
            [
                html.Div(
                    html.Div(style={
                        "width": f"{pct:.1f}%",
                        "height": "8px",
                        "background": _ACCENT,
                        "borderRadius": "4px",
                        "transition": "width 0.5s",
                    }),
                    style={
                        "width": "100%",
                        "background": _CARD,
                        "borderRadius": "4px",
                        "marginBottom": "6px",
                    },
                ),
                html.Div(
                    f"⏱ {_fmt(elapsed)} / {_fmt(total)}",
                    style={"color": _MUTED, "fontSize": "0.85rem"},
                ),
            ],
            style={"marginBottom": "16px"},
        )

        cues = _all_cues(session)
        cur = _current_cue(cues, elapsed)
        nxt = _next_cue(cues, elapsed)

        # 10-second pre-change alert
        alert = None
        if cur and nxt:
            time_to_next = nxt["start_s"] - elapsed
            if 0 < time_to_next <= 10:
                phase = nxt.get("phase", "").replace("_", " ").title()
                alert = html.Div(
                    f"⚠️  Change in {time_to_next:.0f}s — {nxt.get('emoji','')} {phase}"
                    f" · Resistance {nxt.get('resistance', '?')}",
                    style={
                        "background": "#7c2d12",
                        "color": "#fed7aa",
                        "borderRadius": "8px",
                        "padding": "12px 16px",
                        "marginBottom": "12px",
                        "fontWeight": "600",
                    },
                )

        cue_block = None
        if cur:
            track = cur.get("_track", {})
            cue_block = html.Div([
                _cue_card(cur, elapsed),
                html.Div(
                    f"🎵 {track.get('track_name','')} — {track.get('artist','')} · {cur.get('bpm',0):.0f} BPM",
                    style={"color": _MUTED, "fontSize": "0.85rem", "textAlign": "center"},
                ),
            ])
        elif not state.get("running"):
            cue_block = html.Div(
                "Press ▶ Start to begin your coached ride.",
                style={"color": _MUTED, "padding": "32px", "textAlign": "center"},
            )

        next_block = None
        if nxt:
            phase = nxt.get("phase", "").replace("_", " ").title()
            next_block = html.Div(
                f"Next: {nxt.get('emoji','')} {phase} — in {_fmt(nxt['start_s'] - elapsed)}",
                style={"color": _MUTED, "fontSize": "0.9rem", "marginTop": "8px"},
            )

        return progress, alert, cue_block, next_block


_make_display_callback("demo", _DEMO_PATH)
_make_display_callback("ride", _GEN_PATH)


# ── Feedback callbacks ────────────────────────────────────────────────────────

def _make_feedback_callback(tab_id: str, path: Path):
    @app.callback(
        Output(f"feedback-msg-{tab_id}", "children"),
        Input(f"btn-feedback-{tab_id}", "n_clicks"),
        State(f"rating-{tab_id}", "value"),
        State(f"note-{tab_id}", "value"),
        prevent_initial_call=True,
    )
    def submit(n_clicks, rating, note):
        if not n_clicks:
            return ""
        session = _load(path)
        title = session["session"]["title"] if session else "Unknown"
        try:
            import requests
            requests.post(
                "http://localhost:8000/feedback",
                json={"session_title": title, "rating": rating or "", "note": note or ""},
                timeout=3,
            )
        except Exception:
            # Direct write fallback when API is unreachable
            from db.runtime import save_feedback as _db_save
            _db_save(title, rating or "", note or "")
        return "✅ Feedback saved — thanks!"


_make_feedback_callback("demo", _DEMO_PATH)
_make_feedback_callback("ride", _GEN_PATH)


# ── Generate callback ─────────────────────────────────────────────────────────

@app.callback(
    Output("gen-status", "children"),
    Input("btn-generate", "n_clicks"),
    State("playlist-url", "value"),
    State("gen-options", "value"),
    prevent_initial_call=True,
)
def generate(n_clicks, url, options):
    if not n_clicks or not url:
        return ""
    try:
        import requests
        resp = requests.post(
            "http://localhost:8000/session/generate",
            json={
                "playlist_url": url,
                "use_llm": "llm" in (options or []),
                "use_hybrid": "hybrid" in (options or []),
            },
            timeout=120,
        )
        if resp.ok:
            title = resp.json().get("session", {}).get("title", "Session")
            return html.Div(
                [
                    html.Div(f"✅ {title} generated!", style={"color": _GREEN}),
                    html.Div(
                        "Reload the page — the 🎯 Your ride tab will appear.",
                        style={"color": _MUTED, "fontSize": "0.9rem", "marginTop": "4px"},
                    ),
                ]
            )
        return html.Div(f"❌ Error {resp.status_code}: {resp.text[:200]}", style={"color": _RED})
    except Exception as exc:
        return html.Div(f"❌ {exc}", style={"color": _RED})


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("COACHING_PORT", 8501))
    app.run(host="0.0.0.0", port=port, debug=False)

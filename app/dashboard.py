"""
CycleBeat — Plotly Dash Monitoring Dashboard

Replaces the Streamlit monitoring tab with a proper dashboard UI.
Reads feedback from DuckDB (via db.runtime) with JSON fallback.
Auto-refreshes every 30 seconds.
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import dash
from dash import Input, Output, dash_table, dcc, html
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

_DATA_DIR = Path(__file__).parent.parent / "data"
_FEEDBACK_JSON = _DATA_DIR / "feedback.json"

# ── Palette matching the CycleBeat coaching UI ────────────────────────────────
_BG = "#0f0f1a"
_CARD = "#1a1a2e"
_ACCENT = "#4f6ef7"
_RED = "#ef4444"
_GREEN = "#22c55e"
_TEXT = "#e0e0e0"
_MUTED = "#666688"


# ── Data loading ─────────────────────────────────────────────────────────────

def _load_feedback() -> list[dict]:
    """Load feedback from DuckDB; fall back to feedback.json if unavailable."""
    try:
        from db.runtime import get_feedback
        data = get_feedback()
        if data:
            return data
    except Exception:
        pass
    if _FEEDBACK_JSON.exists():
        with open(_FEEDBACK_JSON, encoding="utf-8") as f:
            return json.load(f)
    return []


def _to_df(records: list[dict]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(
            columns=["session", "rating", "note", "timestamp", "date"]
        )
    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.date
    return df


# ── Layout helpers ────────────────────────────────────────────────────────────

def _kpi(label: str, value: str) -> html.Div:
    return html.Div(
        [
            html.Div(
                value,
                style={
                    "fontSize": "2.4rem",
                    "fontWeight": "700",
                    "color": _ACCENT,
                },
            ),
            html.Div(
                label,
                style={
                    "fontSize": "0.85rem",
                    "color": _MUTED,
                    "marginTop": "4px",
                },
            ),
        ],
        style={
            "background": _CARD,
            "borderRadius": "12px",
            "padding": "24px 36px",
            "textAlign": "center",
            "flex": "1",
            "margin": "0 8px",
        },
    )


def _chart_layout(title: str) -> dict:
    return {
        "template": "plotly_dark",
        "paper_bgcolor": _CARD,
        "plot_bgcolor": _CARD,
        "title": {"text": title, "font": {"size": 13, "color": _TEXT}},
        "margin": {"t": 44, "b": 36, "l": 36, "r": 16},
        "font": {"color": _TEXT},
    }


def _empty_fig(label: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        **_chart_layout(label),
        annotations=[
            {
                "text": "No data yet",
                "showarrow": False,
                "font": {"color": _MUTED, "size": 15},
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": 0.5,
            }
        ],
    )
    return fig


# ── App ───────────────────────────────────────────────────────────────────────

app = dash.Dash(__name__, title="CycleBeat — Dashboard")

app.layout = html.Div(
    [
        dcc.Interval(id="tick", interval=30_000, n_intervals=0),

        # Header
        html.Div(
            [
                html.Span(
                    "CycleBeat",
                    style={
                        "fontSize": "1.9rem",
                        "fontWeight": "700",
                        "color": _ACCENT,
                    },
                ),
                html.Span(
                    "  Monitoring Dashboard",
                    style={"fontSize": "1rem", "color": _MUTED},
                ),
            ],
            style={"padding": "28px 32px 8px"},
        ),
        html.Hr(style={"borderColor": _CARD, "margin": "0 32px 24px"}),

        # KPI row
        html.Div(id="kpis", style={"display": "flex", "padding": "0 24px 28px"}),

        # Charts — row 1
        html.Div(
            [
                html.Div(
                    dcc.Graph(id="g-spd", config={"displayModeBar": False}),
                    style={"flex": "1", "margin": "6px"},
                ),
                html.Div(
                    dcc.Graph(id="g-pie", config={"displayModeBar": False}),
                    style={"flex": "1", "margin": "6px"},
                ),
            ],
            style={"display": "flex", "padding": "0 18px"},
        ),

        # Charts — row 2
        html.Div(
            [
                html.Div(
                    dcc.Graph(id="g-hard", config={"displayModeBar": False}),
                    style={"flex": "1", "margin": "6px"},
                ),
                html.Div(
                    dcc.Graph(id="g-cum", config={"displayModeBar": False}),
                    style={"flex": "1", "margin": "6px"},
                ),
            ],
            style={"display": "flex", "padding": "0 18px"},
        ),

        # Feedback log
        html.Div(
            [
                html.H3(
                    "Feedback log",
                    style={"color": _TEXT, "padding": "8px 32px 0"},
                ),
                dash_table.DataTable(
                    id="tbl",
                    page_size=10,
                    style_table={"overflowX": "auto", "margin": "0 24px 32px"},
                    style_header={
                        "backgroundColor": _CARD,
                        "color": _TEXT,
                        "fontWeight": "600",
                        "border": f"1px solid {_MUTED}",
                    },
                    style_cell={
                        "backgroundColor": _BG,
                        "color": _TEXT,
                        "border": f"1px solid {_CARD}",
                        "padding": "8px 14px",
                        "textAlign": "left",
                    },
                ),
            ]
        ),

        html.Div(
            "Auto-refreshes every 30 s",
            style={
                "textAlign": "center",
                "color": _MUTED,
                "fontSize": "0.78rem",
                "paddingBottom": "24px",
            },
        ),
    ],
    style={
        "backgroundColor": _BG,
        "minHeight": "100vh",
        "fontFamily": "system-ui, -apple-system, sans-serif",
        "color": _TEXT,
    },
)


# ── Callback ──────────────────────────────────────────────────────────────────

@app.callback(
    [
        Output("kpis", "children"),
        Output("g-spd", "figure"),
        Output("g-pie", "figure"),
        Output("g-hard", "figure"),
        Output("g-cum", "figure"),
        Output("tbl", "data"),
        Output("tbl", "columns"),
    ],
    Input("tick", "n_intervals"),
)
def refresh(_n):
    records = _load_feedback()
    df = _to_df(records)

    _no_data = [
        _kpi("Total sessions", "—"),
        _kpi("Satisfaction", "—"),
        _kpi("This week", "—"),
    ]

    if df.empty:
        empty = _empty_fig
        return (
            _no_data,
            empty("Sessions per day"),
            empty("Rating breakdown"),
            empty("Hard sessions over time"),
            empty("Cumulative sessions"),
            [],
            [],
        )

    total = len(df)
    great_pct = df["rating"].str.contains("Great").sum() / total * 100
    week_ago = (datetime.now() - timedelta(days=7)).date()
    this_week = int((df["date"] >= week_ago).sum())

    kpis = [
        _kpi("Total sessions", str(total)),
        _kpi("Satisfaction", f"{great_pct:.0f}%"),
        _kpi("This week", str(this_week)),
    ]

    # Sessions per day
    spd = df.groupby("date").size().reset_index(name="sessions")
    fig_spd = px.bar(
        spd, x="date", y="sessions",
        color_discrete_sequence=[_ACCENT],
    )
    fig_spd.update_layout(**_chart_layout("Sessions per day"))

    # Rating pie
    fig_pie = px.pie(
        df, names="rating", hole=0.42,
        color_discrete_sequence=[_ACCENT, _GREEN, _RED],
    )
    fig_pie.update_traces(textinfo="percent+label")
    fig_pie.update_layout(**_chart_layout("Rating breakdown"))

    # Hard sessions over time
    df["is_hard"] = df["rating"].str.contains("Hard").astype(int)
    hard = df.groupby("date")["is_hard"].sum().reset_index()
    fig_hard = px.line(
        hard, x="date", y="is_hard", markers=True,
        color_discrete_sequence=[_RED],
    )
    fig_hard.update_yaxes(title="Count")
    fig_hard.update_layout(**_chart_layout("Hard-rated sessions over time"))

    # Cumulative
    spd["cum"] = spd["sessions"].cumsum()
    fig_cum = px.line(
        spd, x="date", y="cum", markers=True,
        color_discrete_sequence=[_ACCENT],
    )
    fig_cum.update_yaxes(title="Sessions")
    fig_cum.update_layout(**_chart_layout("Cumulative sessions"))

    # Table
    tbl_df = (
        df[["date", "session", "rating", "note"]]
        .sort_values("date", ascending=False)
        .copy()
    )
    tbl_df["date"] = tbl_df["date"].astype(str)
    cols = [{"name": c.title(), "id": c} for c in tbl_df.columns]

    return kpis, fig_spd, fig_pie, fig_hard, fig_cum, tbl_df.to_dict("records"), cols


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("DASH_PORT", 8050))
    app.run(host="0.0.0.0", port=port, debug=False)

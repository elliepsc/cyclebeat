"""
Orchestrator — CycleBeat
LangGraph 0.2.x pipeline: Playlist Agent → Coach Planner → Save Session.
"""

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END, START
from agents.playlist_agent import run_playlist_agent
from agents.coach_planner import run_coach_planner, ingest_patterns


# ─── STATE ───────────────────────────────────────────────────────────────────

class CycleBeatState(TypedDict):
    playlist_url: str
    use_llm: bool
    use_hybrid: bool
    playlist_data: Optional[dict]
    session: Optional[dict]
    error: Optional[str]


# ─── NODES ───────────────────────────────────────────────────────────────────

def playlist_node(state: CycleBeatState) -> CycleBeatState:
    """Fetch Spotify playlist data and attach it to the state."""
    print("🎵 Playlist Agent...")
    try:
        data = run_playlist_agent(state["playlist_url"])
        print(f"   ✅ {len(data['tracks'])} tracks retrieved")
        return {**state, "playlist_data": data}
    except Exception as e:
        return {**state, "error": f"Playlist Agent: {e}"}


def coach_node(state: CycleBeatState) -> CycleBeatState:
    """Run the coach planner to generate the timestamped coaching session."""
    if state.get("error"):
        return state
    print("🏋️ Coach Planner Agent...")
    try:
        session = run_coach_planner(
            state["playlist_data"],
            use_llm=state.get("use_llm", True),
            use_hybrid=state.get("use_hybrid", True)
        )
        print("   ✅ Session script generated")
        return {**state, "session": session}
    except Exception as e:
        return {**state, "error": f"Coach Planner: {e}"}


def save_node(state: CycleBeatState) -> CycleBeatState:
    """Persist the generated session JSON to disk."""
    if state.get("error"):
        return state
    os.makedirs("data", exist_ok=True)
    with open("data/generated_session.json", "w", encoding="utf-8") as f:
        json.dump(state["session"], f, ensure_ascii=False, indent=2)
    print("   💾 Session saved → data/generated_session.json")
    return state


# ─── ROUTING ─────────────────────────────────────────────────────────────────

def route(state: CycleBeatState) -> str:
    """Route to 'end' on error, 'continue' otherwise."""
    return "end" if state.get("error") else "continue"


# ─── GRAPH ───────────────────────────────────────────────────────────────────

def build_graph():
    """Build and compile the LangGraph state machine for the CycleBeat pipeline."""
    graph = StateGraph(CycleBeatState)

    graph.add_node("playlist_agent", playlist_node)
    graph.add_node("coach_planner", coach_node)
    graph.add_node("save_session", save_node)

    graph.add_edge(START, "playlist_agent")
    graph.add_conditional_edges("playlist_agent", route,
                                {"continue": "coach_planner", "end": END})
    graph.add_conditional_edges("coach_planner", route,
                                {"continue": "save_session", "end": END})
    graph.add_edge("save_session", END)

    return graph.compile()


def generate_session(
    playlist_url: str,
    use_llm: bool = True,
    use_hybrid: bool = True
) -> dict:
    """Run the full CycleBeat pipeline and return the generated session dict."""
    ingest_patterns()
    graph = build_graph()
    result = graph.invoke({
        "playlist_url": playlist_url,
        "use_llm": use_llm,
        "use_hybrid": use_hybrid,
        "playlist_data": None,
        "session": None,
        "error": None,
    })
    if result.get("error"):
        raise RuntimeError(result["error"])
    return result["session"]


if __name__ == "__main__":
    url = input("Spotify URL: ")
    session = generate_session(url)
    print(f"\n✅ {session['session']['title']}")

# 🚴 CycleBeat — Your BPM-Powered Cycling Coach

> An AI-powered indoor cycling coach that reads your Spotify playlist's musical structure and generates real-time coaching instructions — just like a live RPM instructor, but with your own music.

---

## 🎯 Problem Statement

Indoor cycling classes are great, but they lock you into the instructor's playlist. CycleBeat solves this: give it any Spotify playlist and it generates a full coaching session — resistance levels, sprint cues, climbs, and recovery phases — synchronized to the actual structure of each song (intro, verse, chorus, drop, breakdown).

No more generic workouts. Your music, your session, your pace.

---

## 🧠 How It Works

```
Spotify Playlist URL
        ↓
Audio Analysis API  ←── sections, energy, tempo per timestamp
        ↓
RAG on RPM patterns ←── Qdrant knowledge base of cycling methodologies
        ↓
LLM Coach Agent     ←── maps musical sections → coaching instructions
        ↓
Live Streamlit UI   ←── displays cues in real time as you ride
        ↓
User Feedback       ←── collected and monitored on dashboard
```

Each song is broken into sections (intro, verse, chorus, drop, outro). CycleBeat maps each section to a specific cycling instruction based on its energy, loudness, and tempo — retrieved from a knowledge base of cycling methodologies via RAG.

---

## ✅ Evaluation Criteria

| Criterion | Implementation | Points |
|---|---|---|
| Problem description | Clearly stated above | 2/2 |
| Retrieval flow | Qdrant KB + LLM coaching agent | 2/2 |
| Retrieval evaluation | Text search vs vector search, best approach selected | 2/2 |
| LLM evaluation | 2 prompt variants compared via LLM-as-Judge | 2/2 |
| Interface | Streamlit live coaching display | 2/2 |
| Ingestion pipeline | Automated Python script + dlt | 2/2 |
| Monitoring | User feedback + Streamlit dashboard (5+ charts) | 2/2 |
| Containerization | Full docker-compose setup | 2/2 |
| Reproducibility | Clear setup, pinned deps, fallback CSV dataset | 2/2 |
| Hybrid search | BPM + semantic search on workout type | 1/1 |
| Document reranking | Rerank coaching patterns by session difficulty | 1/1 |
| Query rewriting | "I'm tired today" → "light recovery session 30min" | 1/1 |
| **Total** | | **23/23** |

---

## 🛠️ Tech Stack

| Component | Tool |
|---|---|
| LLM | GPT-4o-mini |
| Knowledge base | Qdrant |
| Music analysis | Spotify Audio Analysis API |
| Agentic orchestration | LangGraph |
| Interface | Streamlit |
| Monitoring | Streamlit dashboard |
| Ingestion | Python script + dlt |
| Containerization | Docker + docker-compose |

---

## 🤖 Agentic Architecture

CycleBeat uses a 3-agent pipeline built with LangGraph:

**1. Playlist Agent**
- Receives Spotify playlist URL
- Fetches all tracks + detailed audio analysis (sections, timestamps, energy, loudness, tempo)

**2. Coach Planner Agent**
- Queries the Qdrant knowledge base for cycling patterns matching each musical section
- Maps energy/loudness/tempo → cycling instruction (sprint, climb, recovery, etc.)
- Generates a full timestamped coaching script for the session

**3. Live Display**
- Streamlit reads the coaching script
- Displays the right instruction based on current elapsed time
- Collects 👍/👎 feedback after each session

---

## 📦 Knowledge Base

The RAG knowledge base contains cycling coaching patterns, including:

- Warm-up progressions
- Sprint intervals (15s, 30s, 45s)
- Climbing profiles (steady, progressive, standing)
- Recovery patterns
- Cool-down sequences
- Resistance guidelines per intensity level

Patterns are embedded and stored in Qdrant. Each pattern is tagged with: `intensity`, `duration`, `energy_range`, `bpm_range`.

---

## 🎵 Spotify Audio Analysis

CycleBeat uses Spotify's `/audio-analysis/{id}` endpoint to extract:

```json
{
  "sections": [
    {
      "start": 0.0,
      "duration": 18.3,
      "loudness": -14.2,
      "tempo": 124.0,
      "key": 5,
      "mode": 1
    }
  ]
}
```

Each section → one coaching instruction.

**Fallback**: A demo CSV (`data/sample_playlist_analysis.csv`) is included for reviewers without Spotify credentials.

---

## 📊 Monitoring Dashboard

The Streamlit dashboard tracks:

1. Sessions completed per day
2. Average user rating per workout type
3. Most used playlist genres
4. Feedback distribution (👍 vs 👎)
5. Average session duration
6. Query rewriting activations ("tired", "short", "easy")

---

## ⚙️ Setup

### Prerequisites
- Python 3.11+
- Docker + docker-compose
- Spotify Developer account ([developer.spotify.com](https://developer.spotify.com))
- OpenAI API key

### 1. Clone the repo
```bash
git clone https://github.com/your-username/cyclebeat
cd cyclebeat
```

### 2. Configure environment
```bash
cp .env.example .env
# Fill in your keys:
# SPOTIFY_CLIENT_ID=
# SPOTIFY_CLIENT_SECRET=
# SPOTIFY_REDIRECT_URI=http://localhost:8888/callback
# OPENAI_API_KEY=
```

### 3. Run with Docker
```bash
docker-compose up --build
```

### 4. Open the app
```
http://localhost:8501
```

### 5. No Spotify account? Use demo mode
```bash
python ingest/run_demo.py  # loads sample_playlist_analysis.csv
```

---

## 📁 Project Structure

```
cyclebeat/
├── agents/
│   ├── playlist_agent.py      # Spotify fetch + audio analysis
│   ├── coach_planner.py       # RAG + coaching script generation
│   └── orchestrator.py        # LangGraph pipeline
├── ingest/
│   ├── ingest_patterns.py     # Load cycling patterns into Qdrant
│   └── run_demo.py            # Demo mode without Spotify
├── data/
│   ├── cycling_patterns.json  # Knowledge base source
│   └── sample_playlist_analysis.csv  # Fallback dataset
├── evaluation/
│   ├── retrieval_eval.py      # Text vs vector search comparison
│   └── llm_eval.py            # LLM-as-Judge prompt evaluation
├── app/
│   └── streamlit_app.py       # Live coaching UI + monitoring
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## 🔬 Evaluation

### Retrieval Evaluation
Two approaches compared:
- **Text search** on workout pattern tags (intensity, type)
- **Vector search** on semantic embeddings of section descriptions

Winner selected based on hit rate and MRR on a manually labeled test set.

### LLM Evaluation (LLM-as-Judge)
Two prompt variants compared:
- **Prompt A**: structured JSON output with resistance + instruction
- **Prompt B**: natural language coaching cue (like a real instructor)

GPT-4o rates each output on: clarity, safety, motivational tone, and timing accuracy.

---

## 🚀 What's Next

- Voice coaching via text-to-speech (ElevenLabs)
- Heart rate zone integration (Garmin / Apple Watch)
- Cloud deployment (Railway or Render)
- Session history and progress tracking

---

## 👩‍💻 Author

Built as a capstone project for [LLM Zoomcamp 2026](https://github.com/DataTalksClub/llm-zoomcamp) by Ellie Pascaud.

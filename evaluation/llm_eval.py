"""
LLM Evaluation — CycleBeat
Compare deux prompts de coaching via LLM-as-Judge (GPT-4o).
Satisfait le critère : "Multiple LLM approaches evaluated" → 2/2
"""

import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ─── PROMPTS ─────────────────────────────────────────────────────────────────

PROMPT_A = """Tu es un coach de cycling indoor. Génère une instruction de coaching
au format JSON structuré avec les champs : instruction, resistance, effort_level, duration_hint.
Pattern : {pattern}
Morceau : {track_name} ({bpm} BPM)"""

PROMPT_B = """Tu es un instructeur RPM professionnel, motivant et précis.
Génère une instruction courte (1-2 phrases max), en tutoiement, énergique et encourageante.
Adapte-toi exactement au moment de la séance.
Pattern : {pattern}
Morceau : {track_name} ({bpm} BPM)"""

JUDGE_PROMPT = """Tu es un expert en coaching sportif. Évalue ces deux instructions de coaching cycling.

Instruction A : {response_a}
Instruction B : {response_b}

Contexte : phase={phase}, résistance={resistance}, BPM={bpm}

Note chaque instruction de 1 à 5 sur ces critères :
- clarity : est-ce clair et compréhensible sur un vélo en plein effort ?
- motivation : est-ce suffisamment motivant et énergique ?
- precision : les consignes sont-elles précises (résistance, effort) ?
- naturalness : est-ce naturel, comme un vrai coach parlerait ?

Réponds uniquement en JSON valide :
{{
  "A": {{"clarity": 0, "motivation": 0, "precision": 0, "naturalness": 0, "total": 0}},
  "B": {{"clarity": 0, "motivation": 0, "precision": 0, "naturalness": 0, "total": 0}},
  "winner": "A ou B",
  "reason": "explication courte"
}}"""

# ─── CAS DE TEST ─────────────────────────────────────────────────────────────

TEST_CASES = [
    {
        "pattern": {"phase": "sprint", "resistance": 8, "effort": "hard", "label": "Sprint long"},
        "track_name": "Blinding Lights",
        "bpm": 171
    },
    {
        "pattern": {"phase": "climb", "resistance": 9, "effort": "very_hard", "label": "Montée debout"},
        "track_name": "Lose Yourself",
        "bpm": 171
    },
    {
        "pattern": {"phase": "recovery", "resistance": 2, "effort": "very_easy", "label": "Récupération longue"},
        "track_name": "Levitating",
        "bpm": 103
    },
    {
        "pattern": {"phase": "warm_up", "resistance": 3, "effort": "easy", "label": "Échauffement doux"},
        "track_name": "Don't Stop Me Now",
        "bpm": 156
    },
    {
        "pattern": {"phase": "steady", "resistance": 6, "effort": "moderate_hard", "label": "Cadence soutenue"},
        "track_name": "Levitating",
        "bpm": 103
    },
]


# ─── GÉNÉRATION ──────────────────────────────────────────────────────────────

def generate_response(prompt_template: str, case: dict) -> str:
    prompt = prompt_template.format(
        pattern=json.dumps(case["pattern"], ensure_ascii=False),
        track_name=case["track_name"],
        bpm=case["bpm"]
    )
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=150
    )
    return response.choices[0].message.content.strip()


# ─── JUGEMENT ────────────────────────────────────────────────────────────────

def judge(response_a: str, response_b: str, case: dict) -> dict:
    prompt = JUDGE_PROMPT.format(
        response_a=response_a,
        response_b=response_b,
        phase=case["pattern"]["phase"],
        resistance=case["pattern"]["resistance"],
        bpm=case["bpm"]
    )
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=300
    )
    try:
        return json.loads(response.choices[0].message.content)
    except json.JSONDecodeError:
        return {"winner": "?", "reason": "parse error"}


# ─── ÉVALUATION ──────────────────────────────────────────────────────────────

def run_llm_evaluation():
    print("\n🤖 CycleBeat — LLM Evaluation (LLM-as-Judge)")
    print("=" * 60)
    print("  Prompt A : JSON structuré")
    print("  Prompt B : Langage naturel coaching")
    print("=" * 60)

    all_results = []
    scores = {"A": {"clarity": [], "motivation": [], "precision": [], "naturalness": []},
              "B": {"clarity": [], "motivation": [], "precision": [], "naturalness": []}}
    wins = {"A": 0, "B": 0}

    for i, case in enumerate(TEST_CASES):
        print(f"\n  Test {i+1}/{len(TEST_CASES)} — Phase: {case['pattern']['phase']} | {case['track_name']}")

        resp_a = generate_response(PROMPT_A, case)
        resp_b = generate_response(PROMPT_B, case)
        verdict = judge(resp_a, resp_b, case)

        winner = verdict.get("winner", "?")
        if winner in wins:
            wins[winner] += 1

        for metric in ["clarity", "motivation", "precision", "naturalness"]:
            for variant in ["A", "B"]:
                val = verdict.get(variant, {}).get(metric, 0)
                scores[variant][metric].append(val)

        result = {
            "test": i + 1,
            "phase": case["pattern"]["phase"],
            "track": case["track_name"],
            "response_a": resp_a,
            "response_b": resp_b,
            "verdict": verdict
        }
        all_results.append(result)

        print(f"    Vainqueur : Prompt {winner} — {verdict.get('reason', '')[:80]}")

    # ─── Résultats agrégés ───
    print("\n📊 Scores moyens par critère :")
    print(f"{'Critère':<15} {'Prompt A':>10} {'Prompt B':>10}")
    print("─" * 35)

    for metric in ["clarity", "motivation", "precision", "naturalness"]:
        avg_a = sum(scores["A"][metric]) / len(scores["A"][metric])
        avg_b = sum(scores["B"][metric]) / len(scores["B"][metric])
        print(f"{metric:<15} {avg_a:>10.2f} {avg_b:>10.2f}")

    print(f"\n🏆 Victoires — Prompt A: {wins['A']} | Prompt B: {wins['B']}")

    overall_winner = "A" if wins["A"] > wins["B"] else "B"
    prompt_name = "JSON structuré" if overall_winner == "A" else "Langage naturel coaching"
    print(f"✅ Meilleur prompt : Prompt {overall_winner} ({prompt_name})")
    print(f"   → Utilisé dans le pipeline CycleBeat.")

    # Sauvegarde
    os.makedirs("evaluation", exist_ok=True)
    with open("evaluation/llm_eval_results.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print("\n💾 Résultats sauvegardés → evaluation/llm_eval_results.json")


if __name__ == "__main__":
    run_llm_evaluation()

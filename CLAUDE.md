# CLAUDE.md — CycleBeat V3

Instructions projet pour tout coding agent. Dérivé des annexes NORMATIVES
E.0-E.8 de `docs-notes/CYCLEBEAT_PLAN_V3.md` — en cas de doute, lire l'annexe
source ; en cas de conflit, l'ordre des sources de vérité s'applique.

## Sources de vérité (ordre strict — E.0.1)

1. Le code du repo tel qu'il est.
2. `docs-notes/CYCLEBEAT_PLAN_V3.md` Annexe E (contrats d'exécution).
3. Le corps du plan V3.
4. `docs-notes/CYCLEBEAT_PLAN_V2.md` §6-9 (détail du cœur DE).

Conflit détecté → la source la plus haute gagne ET tu le signales.

## Règles d'exécution (E.0)

- **Tu n'inventes rien.** Schéma absent, endpoint ambigu, seuil non spécifié →
  question à l'humain ou 2 options chiffrées. Jamais de comblement silencieux.
- **Une phase = une branche + une PR.** Jamais de commit direct sur main.
  Chaque PR : code + tests + doc + entrée dans `docs/ai-workflow.md`.
- **Definition of done** : `make lint && make test-unit && make dbt` verts.
  Un test qui échoue n'est JAMAIS contourné (pas de skip, pas de xfail sans
  ticket) — corrigé, ou tâche bloquée et remontée.
- **Sections NORMATIVES** (annexes E.2-E.8, runbooks) : conversion en todos
  ligne par ligne, ordre exact, sans omission ni fusion. Chaque comportement
  nouveau embarque son test dans le même commit. Étape jugée inutile →
  question, pas suppression.
- **Fin de tâche** : checklist de phase mise à jour dans la PR + entrée
  ai-workflow.md (prompt/objectif, ce qui a marché, ce que la review humaine
  a corrigé). Invoquer le subagent `ai-workflow-scribe`.

## Interdits absolus (E.0.5)

- Toucher `.env` ou committer un secret (l'historique git est public à terme).
- Modifier `openapi.yaml` sans mettre à jour backend + client front dans la
  MÊME PR.
- Écrire du SQL hors de `api/repositories/` et `dbt/`.
- Ajouter une dépendance sans justification dans la PR.
- Élargir le périmètre d'une phase.
- Introduire une brique payante (E.8) : API payante, SaaS, instance cloud →
  rejet automatique, alternative gratuite ou question.

## Architecture cible (V3 §3, §5)

Pipeline offline : Deezer/Jamendo/CSV → dlt → lake Parquet → resolve BPM
(cross-validation) → DuckDB → dbt (staging → marts). Orchestration Airflow 3
LocalExecutor, 3 DAGs (`dag_ingest`, `dag_resolve_bpm`, `dag_build_warehouse`),
zéro logique métier dans `dags/`.
Couche service : `openapi.yaml` (contrat écrit AVANT le backend) → FastAPI
(routers → services → repositories) → React/Vite/TS (client généré,
appels réseau uniquement via `src/api/`). LLM via LiteLLM → Groq
`qwen/qwen3-32b` (live) / Ollama (demo & CI). Warehouse Copilot : tool-use
borné lecture (E.4). MCP server = les mêmes outils que le copilote.

## Contrats de données normatifs (E.2 — aucune variante autorisée)

- Normalisation BPM : `while bpm > 180: bpm /= 2` puis `while bpm < 70: bpm *= 2`.
- Zones sur bpm_effective : Z1 < 100, Z2 100-115, Z3 116-130, Z4 131-145, Z5 > 145.
- Confidence : 2+ sources d'accord ±3 BPM → 0.9 `cross_validated` ;
  1 source → 0.6 `single_source` ; désaccord > 3 → arbitrage librosa sinon
  0.3 + flag `review` ; aucune source → bpm NULL, exclu du planner.
- Schémas raw/dim/fct : voir E.2 — tout écart = breaking change avec impact
  analysis.

## Garde-fous copilote (E.4 — non optionnels)

query_marts : SELECT unique (sqlglot), allowlist marts, LIMIT 200 injecté,
timeout 5 s. trigger_resolve : cap 10 tracks, confirm=true exigé, journalisé.
Caps de run : max 6 tool calls, question ≤ 500 chars, timeout 60 s, budget
LiteLLM par caller. Les 9 tests de `test_copilot_guards.py` (liste E.4) vivent
dans le MÊME commit que les outils.

## Conventions (E.6)

Python 3.11+, uv + pyproject, ruff + mypy strict sur `cyclebeat/` et `api/`.
Front : pnpm/npm locké. Cibles Makefile : setup, ingest, dbt, api, front,
test-unit, test-integration, eval, audit, lint. Pydantic v2 partout, pas
d'import FastAPI hors de `api/`. Code/identifiants/commits en anglais,
docs en français.

## Coût zéro (E.8 — invariant transverse)

DEMO_MODE par défaut sans aucune clé. Groq free tier avec retry 429 (backoff
expo + jitter, 5 tentatives), max_tokens ≥ 1024 sur les nœuds de génération
(reasoning model). Cache agressif des APIs musique (lake = cache permanent),
pacing ≥ 0,3 s. Toute éval live : échantillon 5 cas d'abord.

## Subagents disponibles (`.claude/agents/`)

- `dbt-reviewer` — sur toute PR touchant dbt/ ou du SQL, avant merge.
- `ai-workflow-scribe` — fin de chaque session/PR (critère 2 de la grille).
- `security-auditor` — phase 0 (hygiène secrets) et phase 10 (5 artefacts crit. 13).
- `contract-guardian` — PRs des phases 4-5 touchant openapi.yaml ou api/.

## Pièges connus

- BPM half-time/double-time : la normalisation E.2 est LA réponse, pas une
  heuristique locale.
- Quotas APIs musique : jamais de re-fetch en CI/review — snapshot demo committé.
- Groq free tier ≈ 6 000 TPM : throttle via LiteLLM en amont, ne pas subir les 429.
- Le repo contient encore des restes v1 (Spotify, Qdrant, LangGraph, Streamlit)
  tant que la phase 0 n'est pas exécutée — ne rien construire dessus.

## Phases

Le §15 du plan V3 fixe les phases et leurs critères de sortie BLOQUANTS.
Avant de coder une phase : reformuler le brief (gabarit E.7 : objectif,
entrées, livrables, validation, hors scope) et le faire valider en mode plan.
Les phases 1 et 9 contiennent des actions humaines : préparer, documenter,
s'arrêter — ne jamais simuler un résultat.

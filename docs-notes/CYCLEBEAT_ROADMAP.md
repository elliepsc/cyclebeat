# CYCLEBEAT — ROADMAP CONSOLIDÉE

> Version : **R1.3 — clôture de la phase 1** (2026-08-15)
> *R1.1 :* grille 2026 (max 32 pts, MCP déplacé crit 2→12), mapping modules↔phases↔critères (§2.6), décision DB Postgres+DuckDB (§2.7), objectif pro « flotte d'agents » (§4.1).
> *R1.2 :* phase 1 synchronisée sur **ADR-005** (backbone = librosa sur preview Deezer ; Jamendo abandonné ; Spotify = import playlist optionnel via ISRC, hors core).
> *R1.3 :* **phase 1 CLOSE** — ADR-005 acté, ADR-004 superseded, rapport de spike chiffré finalisé, `extract_jamendo` retiré de `dag_ingest` (note datée en E.5) ; gate (b) remplie ; phase 2 débloquée.
> **Remplace conceptuellement** `CYCLEBEAT_PLAN_V3.md`, la strate « V3.1 » (durcissements D, jamais matérialisée en fichier) et `CYCLEBEAT_PLAN_V3.2.md`.
> Objectif : **une seule ligne de couches**, du livrable au bonus, avec un statut par phase — au lieu de trois plans parallèles.
> Les **contrats d'exécution normatifs** (Annexe E.0–E.8) restent la référence détaillée : ce document est la *colonne vertébrale*, pas un re-spec. Voir §8.

---

## 0. Pourquoi ce document (refonte du versioning)

Le versioning actuel est une des sources du désordre : trois plans parallèles (`V3`, `V3.1`, `V3.2`) au lieu d'une progression, dont **deux références de vérité pointent vers des fichiers absents** (`CYCLEBEAT_PLAN_V3.1.md` n'existe pas ; `CYCLEBEAT_PLAN_V2.md §6-9` non plus). On remplace cette pile par **deux couches linéaires** :

| Couche | Nom | Ce que c'était avant | Nature |
|---|---|---|---|
| **L0** | **CORE** | Plan V3 (§1–§18) + durcissements « V3.1 » (D1–D8) fondus dedans | **À livrer d'abord.** Non négociable. C'est le 30/30 de la grille + la sécurité/infra. |
| **L1** | **EXTENSIONS** | Plan V3.2 (bonus B1–B7) | **Gaté.** N'ajoute aucun point ; ajoute de la profondeur portfolio. Ne démarre qu'après L0 en ligne. |

Correspondance des fichiers hérités (aucun n'est supprimé — voir §7) :

| Fichier hérité | Devient | Action recommandée |
|---|---|---|
| `CYCLEBEAT_PLAN_V3.md` | **Source de l'Annexe E** (contrats d'exécution) + corps L0 | Conserver **uniquement pour l'Annexe E.0–E.8** ; le reste est repris ici |
| « V3.1 » (D1–D8) | **Sous-section durcissements de L0** (§2.3) | Le fichier canonique n'a jamais existé — dette à clôturer (§7) |
| `CYCLEBEAT_PLAN_V3.2.md` | **Couche L1** (§4) | Conserver comme spec détaillée des modules B1–B7 |
| `CYCLEBEAT_PLAN_V3.2.fr.md`, `MAPPING_FORMATIONS_*` | Inchangés | Référence (mapping formations, blind spots) |
| `BACKLOG*.md`, `*_ultraplan.md`, `ROADMAP_V1/V2*`, `fitflow_*`, `chatgpt.md` | Archives V1/V2 | Candidats à `archive/` (hors périmètre de cette refonte) |

**Ordre des sources de vérité (repris de E.0, inchangé) :** (1) le code du repo tel qu'il est ; (2) l'Annexe E ; (3) ce document (colonne vertébrale L0/L1) ; (4) le corps du plan V3 pour le détail historique. En cas de conflit, la source la plus haute gagne **et on le signale**.

---

## 1. État actuel (snapshot vérifié — `origin/main` = `1b20b40`, 2026-08-15)

| Élément | État |
|---|---|
| **Gate L0 → L1** | 🔴 **FERMÉ** — (b) remplie, (a) et (c) non ; aucun module B ne peut démarrer |
| Phase 0 — Purge & setup | ✅ **DONE** (v1 purgé, hygiène secrets vérifiée, CI verte, ADR-001/002/003) — PR #3, #4 |
| Phase 1 — Spike sources | ✅ **DONE** — ADR-005 acté, ADR-004 superseded, rapport chiffré finalisé sur les 50 pistes mesurées, `extract_jamendo` retiré de E.5. **Aucun compte Jamendo créé.** |
| Phase 2 — Cœur DE | ⬜ **TODO — débloquée** (la phase 1 est close ; c'est la prochaine à ouvrir) |
| Phases 3 → 11 | ⬜ **TODO** — rien démarré |
| Couche L1 (B1–B7) | 🔒 **GATÉE** |

**Ce que la phase 1 a tranché.** Elle s'est close par **une décision, pas par une mesure supplémentaire**. **ADR-005** (supersede ADR-004) fixe le backbone BPM = **`librosa` sur le preview Deezer de 30 s** (vraie musique mainstream, source de métadonnées = source de lecture), le champ `bpm` de Deezer en **enrichissement** et le CSV en socle manuel ; Jamendo/CC est abandonné. Ce chemin était **déjà mesuré** : **82 % de pistes exploitables** (41/50), avec un biais haussier documenté. Le prix accepté, chiffré : **`single_source` 0.6 domine à 54 %**, `cross_validated` 0.9 plafonne à 26 % — car il dépend du champ `bpm` de Deezer, présent sur **23,3 %** des sorties récentes contre **65 %** des classiques. 12 % des pistes restent sans BPM (exclues du planner). Détail : `docs/spikes/phase1-source-coverage.md`.

**Prochain blocage** : plus aucun sur la phase 1. La phase 2 (cœur DE) peut ouvrir — une branche, une PR (E.0).

---

## 2. COUCHE L0 — CORE (à livrer d'abord)

**Définition.** Un produit data end-to-end : pipeline DE observable et testé (Deezer/CSV → lake Parquet → DuckDB modélisé dbt), exposé par une API sous contrat (FastAPI contract-first), consommé par un frontend React, opéré par un **copilote warehouse** (agent tool-use borné), le tout construit avec un workflow AI engineering documenté. Cible : **30/30** de la grille AI Dev Tools + les durcissements sécurité/infra.

### 2.1 Phases (§15 du plan V3, statut à jour)

| Phase | Contenu | Critère de sortie (bloquant) | Statut |
|---|---|---|---|
| **0. Purge & setup** | Purge v1 (Spotify/Qdrant/LangGraph/Streamlit → `archive/v1`), hygiène secrets, CLAUDE.md/AGENTS.md, Makefile, CI squelette, ADR-001 | CI verte sur repo purgé ; aucun secret dans l'historique (vérifié) | ✅ DONE |
| **1. Spike sources** | Couverture Deezer + librosa-preview (déjà mesurée) ; décision backbone **ADR-005** (Deezer preview, Jamendo abandonné) | Rapport chiffré finalisé + ADR-005 acté + ADR-004 superseded | ✅ DONE |
| **2. Cœur DE** | Resolver + cross-validation, 3 DAGs Airflow (`dag_ingest` = `extract_deezer` + `extract_csv`, cf. E.5), lake, DuckDB, dbt (recyclé) | `make ingest && make dbt` à froid **et** 3 DAGs verts ; dbt tests verts ; distribution confidence mesurée | ⬜ TODO — **débloquée** |
| **3. Moteur** | Planner + evaluator + property-based + adversarial + **mutation check** | Mutation check vert | ⬜ TODO |
| **4. Contrat + backend** | `openapi.yaml` (driven par le front), FastAPI en couches, unit + schemathesis | Contrat validé en CI ; tests verts | ⬜ TODO |
| **5. Frontend** | React/Vite/TS, client généré, 4 écrans, vitest | `npm test` vert ; parcours complet local contre l'API | ⬜ TODO |
| **6. LLM & copilote** | LiteLLM + Ollama, CoachingGenerator, **Warehouse Copilot** + outils bornés + éval anti-injection, `fct_llm_calls`/`fct_agent_runs` | Évals coach + copilote vertes en CI (Ollama) ; coût/séance mesuré | ⬜ TODO |
| **7. Extension pack** | skill `new-mart`, subagent `dbt-reviewer`, hooks, **serveur MCP** warehouse, packaging plugin | Chaque brique a servi ≥ 1 fois (preuve dans `ai-workflow.md`) | ⬜ TODO |
| **8. Intégration & compose** | `tests/integration` contre compose complet (api+front+litellm+ollama) | `docker compose up` sur clone propre + suite intégration verte | ⬜ TODO |
| **9. CI/CD & deploy** | Pipeline complet + deploy Render auto sur main vert *(action humaine : secrets Render)* | URL publique vivante ; un push déclenche test→deploy | ⬜ TODO |
| **10. Sécurité & audit** | PR-Agent, Semgrep/Snyk, `agent-security.md`, `ai-policy.md`, diagnostic ops | Les 5 artefacts du §13 committés | ⬜ TODO |
| **11. README & démo** | README, GIF démo, finalisation `ai-workflow.md`, relecture externe | Testé depuis un clone propre par quelqu'un d'autre | ⬜ TODO |

> **Correction de numérotation** (souvent confondue) : le **Warehouse Copilot** — l'agent analytics borné (`query_marts`, garde-fous, tests d'injection) — est construit en **phase 6**. La « §9 » du plan désigne la *section 9* qui le décrit, pas la phase 9. **Phase 9 = déploiement.** Actions humaines : **phase 1** (comptes API du spike) et **phase 9** (secrets Render).

### 2.2 Séquençage au rythme du cours

Phases 0-5 pendant Modules 1-2 · phase 7 pendant Module 3 · phase 10 pendant Module 4. Le projet avance au fil du zoomcamp au lieu de tout garder pour la fin.

### 2.3 Durcissements « série D » (ex-V3.1) — fondus dans L0

Ce sont des correctifs **sécurité/infra** qui renforcent surtout le critère 13 ; ils ne changent aucune phase, ils s'y attachent. (Le fichier canonique V3.1 listant D1–D8 n'a jamais existé dans le repo — les items ci-dessous sont ceux documentés ; voir la dette §7.)

| Durcissement | S'attache à | Effet |
|---|---|---|
| Sandbox DuckDB (`enable_external_access=false`) | Phase 6 — `query_marts` | Empêche l'agent d'atteindre le système de fichiers via SQL |
| Confirmation d'action *out-of-band* | Phase 6 — `trigger_resolve` | Le seul outil « écriture » exige une confirmation hors du canal LLM |
| Défense injection **indirecte** (via la donnée) | Phase 6 / 10 | La donnée lue par l'agent ne peut pas porter d'instruction |
| 2 fichiers DuckDB (single writer) | Phases 2 / 8 | Évite les conflits d'écriture concurrente |
| Pas de disque Render (ADR-003) | Phase 9 | Déploiement sans disque persistant → reproductibilité |
| Frontière BPM-180 (normalisation E.2) | Phases 2 / 3 | Cas limite half/double-time traité par la règle normative, pas une heuristique |
| Ollama caché en CI | Phases 6 / 8 | Évals LLM déterministes et sans coût en CI |

### 2.4 Contrats normatifs

Le détail exécutable (modèle de données, formules de confidence, signatures et garde-fous du copilote, DAGs, conventions, coût zéro) reste **l'Annexe E.0–E.8**. Ne pas le dupliquer ici — voir §8.

### 2.5 Conditions minimales avant soumission (§18)

1. Spike phase 1 documenté avec des **chiffres réels** (seule hypothèse non observée).
2. Mutation check **et** tests d'injection du copilote verts en CI.
3. `docker compose up` + suite d'intégration testés depuis un clone propre **par quelqu'un d'autre**.
4. URL déployée vivante depuis **au moins une semaine** (pas un deploy de dernière minute).
5. `docs/ai-workflow.md` avec **≥ 3 sessions réelles** détaillées (pas une reconstitution).
6. Historique git purgé des `.env`, clés rotées (non négociable — c'est public).

### 2.6 Grille AI Dev Tools **2026** (max **32 pts**) — mapping modules ↔ phases ↔ critères

Le syllabus 2026 a **14 critères** (max **32 pts**, pas 30). Deux nouveautés vs 2025, et elles tombent pile sur ce que L0 planifiait déjà :

- **Crit 12 — Agent Extension Pack (2 pts, nouveau).** MCP **sort du crit 2** (où il était en 2025) et devient sa propre note ici, avec 6 briques : project instructions + 1 workflow/skill + 1 subagent + 1 outil/serveur MCP + 1 hook/guardrail + notes de permissions.
- **Crit 13 — Security/Audit/DevOps (2 pts, nouveau).** 5 artefacts : PR audit + scan déterministe + notes sécurité agent + diagnostic opérationnel + policy outils/données IA.
- **Crit 2 allégé** : « AI-Assisted Development Workflow » (specs, context files, review, verification) — **ne réclame plus MCP**.

Le §16 du plan V3 est **déjà** mappé sur ces 14 critères ; seul le total à afficher change (32, pas 30) et le crit 2 est à alléger.

**Mapping modules du cours → phases L0 → critères :**

| Module cours | Contenu | Phase(s) L0 | Critères visés |
|---|---|---|---|
| **M1** — AI-Native Workflow | spec, AGENTS.md, backlog, rôles PM/SWE/QA, orchestration multi-agents | P0, P1 + `ai-workflow.md` continu | 2 |
| **M2** — Full-stack app | spec, frontend, OpenAPI, backend, DB, unit tests | P4, P5 | 1, 3, 4, 5, 6, 7 |
| **M3** — Test/containerize/deploy | intégration, conteneurs, DB multi-env, CI, deploy, CI/CD | P8, P9 | 8, 9, 10, 11, 14 |
| **M4** — DevOps & Observability | OTel, alerting, **agent first-responder read-only**, audit sécurité récurrent, inventaire permissions | P10 | 13 |
| **M5** — Coding Agent Capabilities | MCP, skills, plugins, hooks, subagents, custom agents | P7 | 12 |

**Discipline de profondeur.** M4 est le module qui déborde le plus (OTel/Loki/Tempo/Grafana complets) : livrer **le minimum qui max le crit 13** (les 5 artefacts), pas une plateforme d'observabilité. Tout le reste des modules est déjà borné par les livrables de phase.

**Alignement de structure (cheap, évite de perdre des points en peer review).** Les reviewers scannent des chemins précis. S'assurer que le repo expose : `product-spec.md`, `openapi.yaml`, `frontend/`, `backend/`, `docker-compose.yml`, `.github/workflows/`, `docs/`, `security/`, `ops/`, et si M5 : `agent-capabilities/`, `agent-hooks/`, `mcp-server/`, `docs/agent-extension-pack.md`, `docs/permissions.md`. Mapper les noms actuels (`dbt/`, `dags/`, `mcp/`, `.claude/`, `docs/security/`) ou ajouter des pointeurs.

### 2.7 Base de données (crit 7 + Module 3) — **Postgres transactionnel + DuckDB analytique**

Le Module 3 enseigne SQLite → **Postgres** (store transactionnel de l'app). CycleBeat est sur **DuckDB**, qui est un entrepôt **analytique** (dbt/marts/copilote) — un rôle différent. Décision (Ellie ouverte à Postgres) : **ne pas remplacer, séparer les rôles** — c'est l'archi réaliste OLTP+OLAP et un bon récit d'entretien :

- **Postgres** = transactionnel : `sessions`, `feedback`, état app (écriture fiable, fin de l'actuel best-effort `try/except pass` — dette E.2 close par la même occasion). Colle au modèle mental du cours, crit 7 + crit 9 plus nets.
- **DuckDB** = entrepôt analytique : lake → DuckDB → dbt (staging→marts), copilote warehouse. **Le différenciateur DE, conservé.**
- Le pipeline ingère les données transactionnelles Postgres dans l'entrepôt pour l'analytique (`fct_session`, `mart_feedback_summary`).

Coût : +1-2 j, 2 stores. **Zéro € préservé** (Postgres en conteneur compose + free tier Render). Alternative minimale si le temps manque : DuckDB-only avec multi-env documenté — **passe** le crit 7 (libellé 2026 générique), mais raconte une histoire moins propre. Reco : la séparation, puisque tu es ouverte.

> **Impact phases :** Postgres transactionnel s'ajoute en **phase 4** (backend/persistance) ; l'entrepôt DuckDB reste **phase 2**. Le durcissement « 2 fichiers DuckDB single-writer » (§2.3) ne concerne plus que l'analytique.

---

## 3. LE GATE (barrière unique L0 → L1)

**Aucun module de la couche L1 ne démarre tant que les trois conditions ne sont pas vraies :**

- **(a)** Le core L0 est **déployé, en ligne, et testé depuis un clone propre**. — ❌
- **(b)** Le spike (phase 1) est **vert** (rapport chiffré). — ✅ **remplie** (2026-08-15, ADR-005)
- **(c)** `homebarista Track 1` est clos (arbitrage inter-projets). — ❌

État courant : **🔴 FERMÉ** (une des trois est remplie). C'est la garde anti-scope-creep — la leçon v1. Un module L1 qui déborde se **coupe**, il ne repousse jamais la soumission.

---

## 4. COUCHE L1 — EXTENSIONS (gaté, après core en ligne)

**Nature (rappel).** +0 point à la grille (déjà 30/30) ; **100 % valeur portfolio/entretien**. Chaque module est **indépendant** : on en prend 0, 1 ou N selon la cible d'emploi, jamais « tout ou rien ». Tout module touchant l'agent (B1) ou la donnée (B3) **hérite des durcissements D**.

| # | Module | Comble | Priorité (objectif DE/AE + agentic) | Effort | Statut |
|---|---|---|---|---|---|
| **B1** | Multi-agent orchestration (copilote → système supervisé) | gap multi-agent (P1) | 🎯 haute | 4–6 j | 🔒 gaté |
| **B5** | Eval + observabilité (judge cross-model, tracing, dashboard, drift) | P3 | ➕ moyenne (cheap, ROI élevé) | 2–3 j | 🔒 gaté |
| **B2** | Batch distribué (Spark, données synthétiques) | gap distribué (P2) | 🎯 haute | 3–4 j | 🔒 gaté |
| **B3** | Streaming (Kafka/Redpanda, Avro) | gap streaming (P2) | 🎯 haute | 3–4 j | 🔒 gaté |
| **B7** | DataOps / data reliability (gates bloquants, Elementary, alerting, runbook) | profondeur DataOps | ➕ moyenne-haute | 3–4 j | 🔒 gaté |
| **B4** | Cloud warehouse + IaC (BigQuery/MotherDuck, Terraform, backfills/SLA) | gap cloud + IaC + orchestration prod | ➕ moyenne | 3–4 j | 🔒 gaté |
| **B6** | Kubernetes + K8sGPT | gap K8s/ops | ⚪ basse (seulement si cible DevOps) | 2–3 j | 🔒 gaté |

**Ordre recommandé (ROI décroissant pour ta cible) :** **B1 → B5 → B2/B3 → B7 → B4 → (B6)**.
**Règle de coupe :** si le temps manque, **B1 + B5 + B7 + (B2 ou B3)** constitue déjà un portfolio « DE/AE + agentic + DataOps » bien au-dessus de la moyenne. B4/B6 = confort.

**Deux honnêtetés de reviewer à tenir** (sinon le module se retourne contre toi) :
- **B2/B3** : sur 40 patterns, distribué et streaming sont *architecturalement injustifiés* → **données synthétiques obligatoires + ADR « quand c'est justifié »**. Jamais de claim « Spark est nécessaire au vrai volume ».
- **B1** : doit **prouver un gain** (trajectory eval, coût vs mono-agent) — sinon c'est de la complexité pour le décor.

Spec détaillée de chaque module : `CYCLEBEAT_PLAN_V3.2.md` §2.

### 4.1 Objectif pro : piloter une flotte de petits agents — **3 emplacements, sans casser le gate**

Ce n'est pas du scope-creep : c'est un objectif de carrière (agents d'analyse/conseil/alerte sur tes tâches). Bonne nouvelle — il s'exerce à **trois endroits distincts** du projet, dont deux **immédiatement** :

| Emplacement | Ce que tu pilotes | Quand | Note grille |
|---|---|---|---|
| **Process (M1)** | Une flotte d'**agents de dev** (planner / implémenteur / `dbt-reviewer` / QA) pour dérouler le backlog du core | **MAINTENANT** — c'est littéralement M1 (« agent loops and multi-agent orchestration ») | Crit 2 + Crit 12 |
| **Ops (M4)** | Un agent **read-only first-responder** : lit les métriques/logs, diagnostique, **alerte** — ne modifie pas | Phase 10 | Crit 13 |
| **Produit (B1)** | Copilote warehouse → **système supervisé** (superviseur + workers `analyst`/`lineage`/`coaching`) — le plus proche de ton besoin pro « agents d'analyse sur données » | **GATÉ** (après core en ligne) | Portfolio (+0 pt) |

Donc tu n'as pas à choisir entre « m'y mettre tout de suite » et « respecter le gate » : **le process (M1) te fait piloter une flotte dès la construction du core**, l'ops (M4) ajoute l'agent d'analyse/alerte, et le produit (B1) reste le morceau supervisé multi-agent, après. Ton besoin pro (analyse/conseil/alerte, **pas** modification autonome) est exactement le profil *borné/read-only* que le cours valorise.

**Coût infra = zéro nouveau.** Une flotte d'agents = les **mêmes** appels LLM, juste orchestrés. Ta stack actuelle suffit : **LiteLLM** (passerelle unique) → **Groq free tier** `qwen3-32b` (live) / **Ollama** local (demo & CI). Le pattern « un modèle différent par agent » (routing par profil) se fait via LiteLLM, gratuitement. **Pas d'API LLM payante, pas de compte cloud** : le seul « cloud » est Render free tier pour le *déploiement* (déjà prévu, crit 10). BigQuery/MotherDuck seulement si tu fais B4 (hors core). Seule vraie contrainte : le TPM Groq free (~6 000) — LiteLLM throttle en amont, Ollama en CI.

**Framework : les patterns d'abord, l'outil ensuite.** La compétence transférable en entreprise, ce sont les *patterns* (superviseur/routeur, orchestrator-worker, hand-off, tool-use borné, tracing, guardrails), pas un framework précis. Pour l'ancrage marché/entretien, **LangGraph** reste le choix sûr (ton ADR-B1 le pose déjà : LangGraph vs superviseur léger). **Hermes Agent** (open-source MIT, multi-agent, agent-to-agent, board Kanban de state partagé) est réel et monte en 2026, mais **jeune (pré-1.0)** et fast-moving — à *observer*, pas à en faire le socle d'une compétence pro ni d'un livrable portfolio. Et **hors grille** pour le certificat : le projet noté attend MCP/skills/hooks/subagents, pas un runtime multi-agent tiers. Verdict : apprends les patterns sur B1 avec LangGraph (ou un superviseur maison) ; garde Hermes pour une veille perso.

---

## 5. Vue linéaire d'ensemble

```
L0 · CORE (livrable — 30/30 + durcissements D)
  P0 ✅ ─ P1 ✅ ─ P2 ⬅ ─ P3 ─ P4 ─ P5 ─ P6(copilote) ─ P7(MCP) ─ P8 ─ P9(deploy) ─ P10 ─ P11
                                                                                      │
                                                            ┌───────── GATE 🔴 ───────┘
                                                            │  (a) core déployé + testé clone propre
                                                            │  (b) spike vert   (c) homebarista T1 clos
                                                            ▼
L1 · EXTENSIONS (bonus portfolio, +0 pt)
  B1 ─ B5 ─ (B2 | B3) ─ B7 ─ B4 ─ (B6)
```

---

## 6. Prochaine action

1. ~~**Clore la phase 1**~~ — ✅ **FAIT (2026-08-15)** : ADR-005 acté (backbone = librosa sur preview Deezer ; Jamendo abandonné ; source = vraie musique mainstream), ADR-004 marqué `Superseded`, rapport de spike finalisé sur les 50 pistes mesurées, `extract_jamendo` retiré de `dag_ingest` (note datée en E.5) et toute dépendance Jamendo retirée du repo. **Aucun compte Jamendo créé.**
2. **Ouvrir la phase 2 (cœur DE)** — resolver + cross-validation, 3 DAGs, lake, DuckDB, dbt. Entrées chiffrées fournies par la phase 1 : `single_source` 0.6 à 54 %, `cross_validated` 0.9 à 26 %, 12 % sans BPM, 8 % en arbitrage librosa (score non fixé par E.2 — **à trancher par le resolver**, avec le choix de `bpm_effective`).
3. **Phases 3 → 11**, une phase = une branche = une PR (E.0).
4. **Ne pas ouvrir L1** avant que le gate soit vert (seul (b) l'est).

---

## 7. Dettes ouvertes & hygiène versioning

| # | Dette | Pourquoi ça compte |
|---|---|---|
| 1 | **Fichier V3.1 inexistant** (D1–D8 canoniques) | Les durcissements sont dispersés/résumés ; §2.3 les rassemble mais la liste D complète manque → à formaliser ou à considérer close par ce document |
| 2 | ~~**Truth-source #4 absente** (`V2 §6-9`)~~ | ✅ **CLOSE (2026-08-15)** — `CLAUDE.md` ne la référence plus : l'Annexe E est déclarée auto-suffisante, V1/V2 sont des archives hors repo et ne sont jamais source de vérité |
| 3 | **Conflit de langue** | E.6 dit « docs en français » ; CLAUDE.md dit « repo docs in English ». Non tranché — ce document est en FR (docs-notes bilingue toléré) |
| 4 | **Branches mergées non balayées** | `chore/dev-env-setup`, `docs/session-2026-07-sync`, `phase-1/source-spike`, `docs/status-2026-07-29` = `0` commit hors main → suppressibles ; `archive/v1-llm-zoomcamp` = `0` aussi mais **à ne JAMAIS supprimer** |
| 5 | **Entrées `ai-workflow.md` manquantes** (PR #6, #7) | Critère 2 de la grille — le plus souvent perdu en étant écrit après coup |
| 6 | **Drift contrat E.2 ↔ code** (chaîne `feedback`) | `raw.feedback → … → mart_feedback_summary` existe en dbt mais pas dans E.2 ; écriture DuckDB best-effort à fiabiliser ; exposer `mart_feedback_summary` sur l'allowlist du copilote |

---

## 8. Annexe E — contrats d'exécution (normatifs, par référence)

Les contrats normatifs **ne sont pas dupliqués ici** pour éviter le drift : ils restent l'Annexe E.0–E.8 du plan V3 (`CYCLEBEAT_PLAN_V3.md`, lignes 352→577). Ils couvrent :

- **E.0** Règles du modèle exécutant (invent nothing, 1 phase = 1 PR, DoD, interdits).
- **E.1** État vérifié du repo + runbook Phase 0.
- **E.2** Contrats de données (raw/dim/fct, normalisation BPM, confidence).
- **E.3** Contrat API (schémas endpoints critiques).
- **E.4** Copilote — signatures & garde-fous (query_marts sqlglot SELECT-only, allowlist, LIMIT 200, timeout 5 s, caps 6 tool-calls, tests d'injection nommés).
- **E.5** DAGs Airflow.
- **E.6** Conventions (Python 3.11+, uv, ruff/mypy, couches API, cibles Makefile).
- **E.7** Gabarit de brief de phase.
- **E.8** Coût zéro (invariant transverse).

> **Option de consolidation totale** (non faite ici, à ta main) : si tu veux un fichier *unique* auto-suffisant, copier l'Annexe E telle quelle à la fin de ce document, puis déplacer `CYCLEBEAT_PLAN_V3.md` en `archive/`. Tant que ce n'est pas fait, garde le plan V3 **pour son Annexe E uniquement**.

---

*CycleBeat — Roadmap consolidée R1.3 — refonte du versioning (L0 core / L1 extensions) — août 2026.*
*Sources : CYCLEBEAT_PLAN_V3.md (§15 phases, Annexe E), CYCLEBEAT_PLAN_V3.2.md (modules B1–B7), MAPPING_FORMATIONS_CYCLEBEAT.md (durcissements D, priorités), `docs/adr/adr-005-deezer-preview-backbone.md` + `docs/spikes/phase1-source-coverage.md` (clôture phase 1), statut d'exécution 2026-08-15 (`origin/main` 1b20b40).*

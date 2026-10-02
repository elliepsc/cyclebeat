# CYCLEBEAT V3.2 — ULTRAPLAN (couche BONUS sur V3.1)
## Pipeline DE + agentique — extension « profondeur & portfolio » (angles morts + 3 priorités)

> Version : 3.2 — Juillet 2026 · **Version française** (jumelle de `CYCLEBEAT_PLAN_V3.2.md`, anglais).
> **Étend** CYCLEBEAT_PLAN_V3.1.md (ne le remplace pas). V3.1 est conservé **intégralement**,
> D1–D8 compris. V3.2 n'ajoute **aucune** modification au *core* : il ajoute une **couche bonus
> optionnelle** (modules B1–B6), activée **après** la soumission du core.
> But : combler les angles morts identifiés et exécuter les 3 priorités, pour un signal
> **Data Engineer / Analytics Engineer avec LLM & agentique** — sans casser la contrainte coût zéro
> ni le contrôle de périmètre qui a sauvé le projet du piège v1.

---

## ÉTAT D'EXÉCUTION — mis à jour le 2026-07-29

> **État mutable, pas du contenu de plan.** Cette section consigne où en est réellement
> l'exécution ; le reste du fichier est la spécification bonus et ne bouge pas avec elle. Elle est
> placée ici parce que la règle 3 du §0 conditionne chaque module bonus à l'avancement du core —
> en particulier 3(b), *« le spike sources (phase 1) est vert »*. Vérifié contre
> `origin/main` = `6e8039f`, pas de mémoire.

### 🔴 Gate bonus : FERMÉE — aucun module B ne peut démarrer

| Condition règle 3 du §0 | État |
|---|---|
| (a) Core V3.1 déployé, vivant, testé depuis un clone propre | ❌ Non démarré — les phases 2–11 sont intactes |
| (b) Spike sources (phase 1) vert | ❌ **Outillage livré, mesure non lancée** — voir plus bas |
| (c) `homebarista Track 1` soldé | ❓ Hors périmètre de ce repo, non vérifiable ici |

### Fait

| Phase | État | Preuve |
|---|---|---|
| **0. Purge & setup** | ✅ **FAITE**, critères de sortie atteints | Briques v1 purgées (Spotify/Qdrant/LangGraph/Dash) ; grep `spotipy\|qdrant\|langgraph` sur `api db ingest` vide sur `origin/main` ; hygiène secrets vérifiée et non supposée (`.env` jamais tracké) ; CI `build` **success** sur `main` ; ADR-001/002/003 committés. PR #3, #4. |
| **1. Spike sources** | 🟡 **OUVERTE** — outillage mergé, **mesure non lancée** | PR #7 mergée : `tools/spike/` (script PEP 723 + cœur E.2 stdlib seul), 46 tests unitaires, 3 fixtures committées, runbook, squelette de rapport. **Le critère de sortie §15 — « rapport chiffré » — n'est PAS atteint.** |

Transverse, hors numérotation des phases :

- **Chaîne de truth-sources réparée** (PR #5). `CLAUDE.md` désignait
  `docs-notes/CYCLEBEAT_PLAN_V3.md` comme truth-source #2 alors que `.gitignore` l'excluait :
  quiconque clonait obtenait les règles sans leur source. Les plans, ce fichier et
  `DECISIONS_SESSION_2026-07.md` sont désormais trackés.
- **Filet de sécurité rendu immuable.** Tag annoté `v1-llm-zoomcamp-archive` → `c7bb63a`, poussé
  et vérifié sur origin. La branche `archive/*` ne doit jamais passer au sweep : elle affiche
  `0 commit hors de main` tout en étant le seul pointeur nommé vers l'arbre d'avant-purge.
- **Environnement de dev et workflow de contribution documentés dans le README** (PR #6).
  `make lint && make test-unit` n'était pas exécutable en l'état : Windows et WSL ne peuvent
  partager `.venv/` (`Scripts/` vs `bin/`, `os error 5` sur drvfs), et la procédure
  branche → PR → merge ne vivait que dans une note locale gitignored.

### Reste à faire — dans l'ordre

1. **Clore la phase 1. Bloquant, et cela demande une action humaine.** Selon E.7 le modèle
   prépare et s'arrête ; un résultat de spike n'est jamais simulé.
   - Créer un `client_id` Jamendo gratuit (**le décisif** — il débloque l'audio CC complet sur
     lequel se mesure le socle ADR-004). Optionnellement une clé GetSongBPM, qui impose un
     **backlink obligatoire**. Deezer ne demande aucune clé.
   - Lancer `tools/spike/source_coverage.py` (commencer par un échantillon 5 cas, E.8), committer
     `data/spike/raw_output.json`, remplir `docs/spikes/phase1-source-coverage.md` à partir de lui.
   - Appliquer la règle §15 : **Deezer exploitable < 50 % → recommander le pivot CSV + Jamendo +
     librosa**. Promouvoir ADR-004 de `Accepted (principle)` à `Accepted` chiffré, ou écrire
     ADR-005 si librosa déçoit.
2. **Phases 2–11 : non démarrées.** Rien ne peut commencer avant la clôture de la 1 — règle
   bloquante du §15.
3. **Dettes à solder** (ci-dessous).

### Dettes ouvertes et conflits signalés

| # | Élément | Pourquoi ça compte |
|---|---|---|
| 1 | **Entrées `docs/ai-workflow.md` manquantes pour les PR #6 et #7** | `CLAUDE.md` exige une entrée par PR ; c'est le critère 2 de la grille, le plus souvent perdu parce que rédigé a posteriori. Rattrapé dans la même PR que cet état. |
| 2 | **Conflit de langue, non résolu** | Le §E.6 du V3 dit *« docs en français »* ; `CLAUDE.md` dit *« repo docs in English »*. Tranché vers l'anglais par l'ordre des truth-sources (le repo tel qu'il est — 12 ADR, README, ai-workflow sont anglais). **Le texte du plan n'a délibérément pas été édité** : amender une truth-source n'est pas un effet de bord. Décision à prendre. |
| 3 | **La truth-source #4 n'existe pas** | `CLAUDE.md` cite `docs-notes/CYCLEBEAT_PLAN_V2.md §6-9` comme truth-source #4, et E.2 dit *« reprendre V2 §6 comme spec normative »*. **Ce fichier n'est pas dans le repo.** E.2 se suffit, donc rien n'a été inventé — mais la référence est invérifiable. |
| 4 | **Deux désambiguïsations E.2** portées par `tools/spike/e2.py` | E.2 est écrit pour des entiers ; le code manipule des flottants. Les zones sont attribuées sur le BPM arrondi (aucun flottant ne tombe entre deux bandes), et comme E.2 fixe les *scores* de confidence mais pas quelle valeur devient `bpm_effective`, le spike prend la moyenne des sources concordantes et reporte l'arbitrage librosa dans son propre bucket plutôt que d'inventer un score. **Le resolver de phase 2 devra trancher proprement.** |
| 5 | **Branches mergées non nettoyées** | `chore/dev-env-setup`, `docs/session-2026-07-sync`, `phase-1/source-spike` affichent toutes `0` commit hors de `main` et peuvent être supprimées. `archive/v1-llm-zoomcamp` affiche `0` aussi et ne doit **jamais** l'être. |

---

## 0. NATURE DE V3.2 — À LIRE AVANT TOUT

Trois règles non négociables, dans l'esprit reviewer senior :

1. **Le core V3.1 (30/30) reste la priorité absolue et n'est pas touché.** V3.2 ne modifie pas une ligne
   des phases 0–11. Un module bonus qui exigerait de changer le core est **rejeté**.
2. **Les bonus n'ajoutent AUCUN point au zoomcamp** (la grille est déjà à 30/30). Ils ajoutent de la
   **profondeur portfolio** et du **signal entretien**. Donc on ne les fait **jamais** au détriment de la
   soumission : les faire pour le CV/entretien, pas pour la note.
3. **Gating strict (anti-scope-creep — la leçon du v1).** Aucun module bonus ne démarre tant que :
   (a) le core V3.1 est **déployé, vivant, et testé depuis un clone propre** ; (b) le spike sources (phase 1)
   est vert ; (c) `homebarista Track 1` est soldé (arbitrage inter-projets §0.4 du V3.1). Chaque bonus est
   **indépendant** : on en prend 0, 1 ou N selon la cible d'emploi visée, jamais « tout ou rien ».

Discipline d'exécution héritée (E.0 du V3.1, s'applique telle quelle à V3.2) : un module = une branche + une PR ;
chaque comportement embarque son test dans le même commit ; un ADR par décision structurante ; entrée
`docs/ai-workflow.md` à chaque session ; **toute brique payante = rejet automatique** (E.8).

### 0.1 Ce que V3.2 adresse (rappel angles morts + 3 priorités)

| Manque / priorité (source : mapping formations) | Module bonus | Priorité pour ton objectif |
|---|---|---|
| **Priorité 1 — multi-agent / orchestration** (gap #1 de Cyclebeat, ton envie explicite) | **B1** | 🎯 haute |
| **Priorité 2 — DE à l'échelle : batch distribué (Spark)** (angle mort) | **B2** | 🎯 haute |
| **Priorité 2 — DE à l'échelle : streaming (Kafka)** (angle mort) | **B3** | 🎯 haute |
| Angle mort — **cloud warehouse managé + IaC** (BigQuery/MotherDuck, Terraform) | **B4** | ➕ moyenne |
| **Priorité 3 — éval + observabilité approfondies** (judge cross-modèle, tracing, drift) | **B5** | ➕ moyenne (peu chère, fort ROI) |
| Angle mort — **Kubernetes / ops** (K8s, K8sGPT) | **B6** | ⚪ basse (seulement si cible DevOps) |
| **Plus de DataOps** — fiabilité data : quality gates, observabilité, freshness/anomalies, alerting, runbook incident | **B7** | ➕ moyenne-haute (peu cher, fort signal DataOps) |
| Angle mort — **orchestration *en prod*** (backfills, SLA, data contracts) | intégré à **B4** / **B7** | ➕ moyenne |

> **Note de bouclage.** Ta toute première question — *« pour faire de l'orchestration multi-agent, sur quel
> projet ? »* — trouve ici sa réponse propre : **Cyclebeat, via le module B1**, en bonus *après* le core.
> Le copilote mono-agent du V3.1 (délibérément borné) devient le socle d'un système multi-agents supervisé.

---

## 1. VUE D'ENSEMBLE DU BONUS TRACK

| # | Module | Comble | Ajoute (profondeur) | Outils (0 €) | Effort | Formation mappée |
|---|---|---|---|---|---|---|
| B1 | Orchestration multi-agents | gap multi-agent · P1 | supervisor/router, orchestrator-worker, hand-off, mémoire de thread, tracing par agent | LangGraph (ADR) ou supervisor framework-light ; même LLM | 4–6 j | Blent Agentic AI · Maven Agent Eng · Alexey |
| B2 | Batch distribué Spark | gap distribué · P2 | DataFrame API, joins/groupBy, partitions, shuffles, parité DuckDB | PySpark local | 3–4 j | Blent DE · DE Zoomcamp M6 |
| B3 | Streaming Kafka | gap streaming · P2 | producteur→topic→consumer, mart temps réel, schémas Avro/registry | Redpanda (compose) | 3–4 j | Blent DE · DE Zoomcamp M7 |
| B4 | Warehouse cloud + IaC | gap cloud managé + IaC + orchestration prod | dbt multi-adapter (BigQuery/MotherDuck), Terraform, backfills/SLA/data contracts | BigQuery free / MotherDuck free · Terraform CLI | 3–4 j | DE Zoomcamp M1/M3/M4 · Blent DE · GDE Archi |
| B5 | Éval + observabilité | P3 | **judge cross-modèle**, tracing agent, dashboard coût/latence, drift | Langfuse self-host · OpenTelemetry · Grafana · Evidently | 2–3 j | Alexey · Blent Agentic AI · GDE |
| B6 | Kubernetes + K8sGPT | gap K8s/ops | déploiement kind, diagnostic opérationnel IA | kind · Helm · K8sGPT | 2–3 j | Blent DevOps · GDE DevOps/Archi |
| B7 | DataOps / fiabilité data | profondeur DataOps · orchestration prod | quality gates bloquants, observabilité, freshness/anomalies, alerting, slim CI, promotion d'env, runbook incident | Elementary · dbt · GitHub Actions | 3–4 j | Blent DE · DE Zoomcamp M4 · Alexey · GDE |

Total bonus : **~20–28 j** au-dessus des 32–40 j du core. **Jamais en parallèle du core.** À étaler
post-soumission, par priorité de carrière (§3).

---

## 2. MODULES BONUS — SPÉCIFICATIONS

Chaque module suit le gabarit E.7 du V3.1 (Objectif / Entrées / Livrables / Validation / Hors scope) et
hérite des garde-fous D1–D8 quand il touche à l'agent, la donnée ou le déploiement.

### B1 — Orchestration multi-agents (Warehouse Copilot → système supervisé) 🎯

**Objectif.** Transformer le copilote mono-agent (V3.1 §9) en **système multi-agents supervisé**, sans
sacrifier un seul garde-fou D1/D2/D5.

**Ce que ça démontre.** Supervisor/routing · orchestrator-worker · hand-off · mémoire de thread partagée ·
contrôle de terminaison (caps) · **tracing par agent modélisé dans le warehouse** — exactement le module
multi-agents de Blent Agentic AI et les patterns orchestrator-worker/A2A de Maven.

**Design normatif.**
- **Superviseur** (routeur) reçoit la question, choisit UN worker, agrège, termine. Il n'exécute jamais de SQL.
- **Workers spécialisés**, chacun borné : (1) `warehouse-analyst` = le copilote actuel (SELECT-only, connexion
  sandboxée D1) ; (2) `lineage-explainer` = `explain_track` en profondeur ; (3) `coaching-agent` = génération/
  explication de séance. Chaque worker **conserve** ses garde-fous — la sécurité se *compose*, elle ne se dilue pas.
- **Aucune fusion des périmètres** : un worker ne peut pas appeler les outils d'un autre. `trigger_resolve`
  reste soumis à la confirmation hors-bande D2, **au niveau du superviseur comme du worker**.
- **Framework** : décision par ADR. Option A (recommandée pédagogiquement) = **LangGraph**, réintroduit ici
  *à bon escient* (graphe réel : branchement + état partagé + N agents — ce que les 3 nœuds linéaires du v1 ne
  justifiaient pas ; ADR-B1 documente « quand un graph framework devient légitime »). Option B = superviseur
  framework-light (function-calling) si tu veux rester sans dépendance. **Choisis-en une, argumente en ADR.**
- **Observabilité** : étendre `fct_agent_runs` avec `agent_name`, `role` (supervisor|worker), `parent_run_id`,
  `handoff_reason`. Nouveau mart `mart_agent_topology` (qui appelle qui, coût par agent).

**Éval & critère de sortie (anti-circulaire, esprit V2 §9).**
- Golden set de **12 questions de routage** avec worker-cible attendu ; le superviseur route juste ≥ 11/12.
- **Trajectory eval** : pas de hand-off inutile ; coût/latence vs baseline mono-agent **mesurés et documentés**
  (un multi-agent qui coûte 3× sans gain = anti-pattern à assumer ou corriger).
- **Test anti-contournement** : une question piégée ne doit pas permettre à un worker de sauter ses garde-fous
  via le superviseur (`test_supervisor_cannot_bypass_worker_guards`).
- Tourne en CI sur Ollama. Sortie : évals vertes + note de décision « single vs multi-agent : quand c'est justifié ».

**Pitch entretien.** *« Système multi-agents supervisé au-dessus d'un warehouse : un routeur dispatche vers des
agents spécialisés bornés, chacun durci contre l'injection directe ET indirecte, avec un tracing par agent
modélisé en SQL dans le warehouse — et une éval de trajectoire qui prouve que le multi-agent apporte un gain
réel vs le mono-agent, pas juste de la complexité. »*

**Hors scope.** Pas d'A2A inter-process, pas de voice, pas d'agents autonomes en écriture (D2 tient).

### B2 — Batch distribué avec Spark 🎯

**Objectif.** Prouver la compétence **calcul distribué** — le gap DE le plus visible du marché.

**Design normatif.**
- Réimplémenter `dag_build_warehouse` (ou l'agrégation la plus lourde) en **PySpark local** (gratuit), en
  écrivant du Parquet que le warehouse relit — **même contrat de sortie** que le chemin DuckDB.
- **Honnêteté d'échelle (obligatoire, ADR-B2).** 40 patterns = volume trivial → Spark y est *injustifié*. Donc :
  générer un **dataset synthétique large** (10–50 M d'événements d'écoute / résolutions simulées) pour rendre
  Spark pertinent. L'ADR pose la règle : « DuckDB par défaut ; le chemin Spark est un *spike d'échelle* qui
  prouve la maîtrise du distribué, justifié au-delà de ~X Go ». **Ne jamais prétendre que Spark est nécessaire
  au vrai volume** — un reviewer le verrait.
- Démontrer : DataFrame API, groupBy/join, partitionnement, broadcast join, compréhension des shuffles.
- Cible Makefile `spark-build` ; profil compose `spark` optionnel.

**Critère de sortie.** Job Spark traite le dataset synthétique 10 M lignes ; **test de parité** (Spark vs DuckDB
sur le petit set → résultats identiques) ; benchmark documenté ; ADR-B2 écrit.

**Mappe** Blent DE (Spark/Hadoop), DE Zoomcamp M6.

### B3 — Streaming avec Kafka/Redpanda 🎯

**Objectif.** Prouver la compétence **temps réel** — second gap DE majeur.

**Design normatif.**
- Chemin streaming : un **producteur** simule des événements live (télémétrie de séance / « now playing ») →
  **topic Kafka** (Redpanda dans compose, gratuit, API Kafka-compatible + schema registry) → **consumer** qui
  atterrit dans le lake et met à jour un **mart temps réel** (ex. `mart_live_session` ou feedback roulant).
- **Gestion de schéma** : Avro + schema registry Redpanda ; un message non conforme est rejeté et compté.
- Profil compose `streaming`, opt-in (l'app tourne sans). Kafka Streams optionnel ; un consumer Python suffit.

**Critère de sortie.** Bout-en-bout producteur→topic→consumer→mart vert ; schéma Avro appliqué (test de message
non conforme rejeté) ; 1 test d'intégration `@streaming` ; documenté (README + ADR-B3 : batch vs streaming, quand).

**Mappe** Blent DE (Kafka + Spark Streaming), DE Zoomcamp M7.

### B4 — Warehouse cloud managé + IaC + orchestration prod ➕

**Objectif.** Combler « cloud managé », « IaC » et « orchestration *en prod* » d'un coup — tout en free tier.

**Design normatif.**
- **dbt multi-adapter** : ajouter **BigQuery** (free tier : 1 To de requêtes/mois gratuit) *ou* **MotherDuck**
  (free tier) comme cible alternative, sélectionnée par env `WAREHOUSE_TARGET`. Les mêmes modèles dbt buildent
  sur les deux (c'est précisément le M4 du DE Zoomcamp : dbt sur DuckDB **et** BigQuery). Démontrer
  **partitioning/clustering** (BigQuery) et la **conscience du coût requête** (pruning de partition, cap free tier).
- **IaC Terraform** (CLI gratuit) : provisionner le dataset BigQuery + service account/IAM (ou ressources
  MotherDuck). Petit, honnête → comble le M1 du DE Zoomcamp (IaC).
- **Orchestration prod (0 € — approfondir Airflow, pas ajouter d'infra)** : backfills (catchup + runs
  date-partitionnés), **SLA**, **data contracts inter-DAG** (assertions fraîcheur/row-count entre `resolve`→`build`).

**Critère de sortie.** `WAREHOUSE_TARGET=bigquery make dbt` build les mêmes modèles sur le cloud ; `terraform apply`
provisionne le dataset (et `terraform destroy` le retire — pas de coût résiduel) ; un backfill démontré ;
garde-fou coût documenté. ADR-B4 : DuckDB local vs cloud, quand basculer.

**Mappe** DE Zoomcamp M1/M3/M4, Blent DE, GDE Software Architecture (cloud, DR).

### B5 — Éval & observabilité approfondies ➕ (peu chère, fort ROI)

**Objectif.** Professionnaliser la couche éval/monitoring — priorité 3, et corrige un biais réel.

**Design normatif.**
- **LLM-as-judge cross-modèle** : le juge tourne sur un modèle **différent** du générateur (supprime le biais
  d'auto-jugement — le même défaut que j'ai signalé sur homebarista). Ex. génération Groq `qwen3-32b`, juge sur
  un second modèle free. Footnote méthodo dans le README.
- **Tracing** : Langfuse (self-host gratuit dans compose) *ou* OpenTelemetry + export ; instrumenter chaque
  étape d'agent (surtout le multi-agent B1).
- **Dashboard** : Grafana (gratuit) sur `fct_llm_calls` / `fct_agent_runs` (export DuckDB→Parquet/Postgres, ou
  connecteur CSV/Infinity) → coût, latence, usage d'outils, coût par agent.
- **Drift** : Evidently (gratuit) sur les métriques de qualité données + métriques de sortie LLM dans le temps.
- Étendre le golden set + brancher la trajectory eval de B1.

**Critère de sortie.** Juge sur modèle distinct ; traces Langfuse visibles ; **1 dashboard Grafana** live ;
**1 rapport Evidently** committé. ADR-B5 : pourquoi juge cross-modèle.

**Mappe** Alexey (judge, Grafana, Logfire/OpenTelemetry, Evidently, LangWatch), Blent Agentic AI (éval/golden/traces),
GDE (token cost / inference profiling / data drift).

### B6 — Déploiement Kubernetes + K8sGPT ⚪ (optionnel, cible DevOps)

**Objectif.** Le seul module hors ta trajectoire cœur ; à faire **uniquement** si tu vises des rôles
DevOps-adjacents. Le V3.1 le mentionnait déjà comme « optionnel si le temps le permet » — ici il est cadré.

**Design normatif.** Déployer la stack compose sur un **cluster kind local** (gratuit) : manifests/Helm ; puis
**K8sGPT** pour le diagnostic opérationnel (améliore l'artefact « operational diagnosis » du crit. 13).

**Critère de sortie.** Stack tourne sur kind ; diagnostic K8sGPT d'une panne injectée documenté. ADR-B6.

**Mappe** Blent DevOps (K8s), GDE DevOps, GDE Software Architecture (sécurité/ops IA).

### B7 — DataOps / data reliability engineering ➕ (peu cher, fort signal DataOps)

**Objectif.** Rendre la *fiabilité* du pipeline first-class — le « plus de DataOps » que tu demandes.
Consolider les fils DataOps déjà présents dans le core (dbt tests, CI, mutation check, marts data quality, B4
backfills/SLA/contracts) en une couche explicite et démontrable, et ajouter ce qui manque : quality gates
bloquants, observabilité, monitoring d'anomalies, alerting, et un runbook d'incident data.

**Ce que ça démontre.** Data reliability engineering — la discipline que les rôles DE/AE attendent de plus en
plus : « comment *sais-tu* que le pipeline est sain, et que se passe-t-il quand il ne l'est pas ? »

**Design normatif.**
- **Quality gates bloquants en CI** (pas juste des warnings) : au-delà des tests dbt, ajouter dbt `source
  freshness` + anomalie de volume + détection de changement de schéma qui **font échouer** le build. Outil :
  Elementary Data (OSS, dbt-natif) ou tests dbt custom. Une source périmée/anormale arrête le pipeline, elle
  ne part pas en prod en silence.
- **Observabilité data** : Elementary produit un rapport data-quality (résultats de tests, freshness, volume,
  anomalies dans le temps) + lineage, committé comme artefact (et/ou exposé sur l'écran Data Quality).
- **Slim CI pour dbt** : sélection par état (`dbt build --select state:modified+`) → une PR ne rebuild que les
  modèles changés — LE geste DataOps analytics-engineering.
- **Promotion d'environnement** : cibles dbt `dev` (DuckDB local) / `ci` / `prod`, flux de promotion documenté ;
  une branche de feature n'écrit jamais en prod.
- **Alerting (0 €)** : alertes échec de pipeline + anomalie data via notification GitHub Actions / callback
  SLA-miss Airflow — aucun SaaS payant.
- **Runbook d'incident data** : `docs/runbooks/data-incident.md` — triage → rollback de l'image warehouse →
  re-run du DAG → communication. Se branche directement sur l'artefact « operational diagnosis » du crit. 13.

**Critère de sortie.** Un gate freshness/qualité cassé **fait échouer la CI** (prouvé avec une fixture périmée/
anormale volontaire) ; rapport Elementary committé ; sélection slim-CI opérante sur une PR ; runbook écrit. ADR-B7.

**Pitch entretien.** *« Le pipeline a des SLO de fiabilité data : gates bloquants freshness/volume/schéma en CI,
un rapport d'observabilité Elementary, de l'alerting d'anomalies, et un runbook d'incident data — donc un mauvais
batch amont échoue bruyamment au lieu d'empoisonner les marts en silence. »*

**Mappe** pratiques DataOps (Blent DE, DE Zoomcamp M4 testing/deploy), Alexey (monitoring/observabilité),
GDE Software Architecture (data drift).

---

## 3. SÉQUENCEMENT RECOMMANDÉ (aligné DE/AE + LLM/agentique)

Ordre par ROI décroissant **pour ta cible**. Chaque module est un jalon indépendant, livré sur sa branche.

1. **B1 — multi-agents.** Ton envie n°1, et le différenciateur agentique. Commence par lui.
2. **B5 — éval/observabilité.** Peu cher, fort signal, et il *outille* B1 (trajectory eval, tracing par agent).
   Faire B1 puis B5 forme un bloc « agentique sérieux » cohérent.
3. **B2 puis B3 — Spark puis Kafka.** Le gap DE « à l'échelle » que ni Cyclebeat ni homebarista ne portent.
   Ce sont eux qui ouvrent les offres DE seniors.
4. **B7 — DataOps.** Peu cher, fort signal ; il approfondit la fiabilité du cœur DE. À faire avec/après B4
   (il réutilise le même warehouse + dbt + Airflow). Excellente matière d'entretien pour des rôles AE/DE-fiabilité.
5. **B4 — cloud + IaC.** Complète le signal DE/AE cloud (BigQuery, Terraform, backfills).
6. **B6 — K8s.** Seulement si tu bascules vers du DevOps. Sinon, ignore-le.

Règle de coupe : si le temps manque, **B1 + B5 + B7 + (B2 ou B3)** est déjà un portfolio « DE/AE + agentique +
DataOps » très au-dessus de la moyenne. B4/B6 sont du confort.

---

## 4. IMPACT GRILLE & RISQUES (lucidité reviewer)

- **Grille zoomcamp : +0 point.** Le core est à 30/30 ; les bonus ne comptent pas pour la note. Leur valeur est
  100 % **entretien/portfolio**. Ne jamais retarder la soumission pour un bonus.
- **Risque « CV-padding » (Spark/Kafka).** Sur 40 patterns, distribué et streaming sont *architecturalement
  injustifiés*. Sans dataset synthétique large + ADR honnête, un reviewer senior lira du name-dropping. → B2/B3
  **exigent** la donnée synthétique et l'ADR « quand c'est justifié ». Mieux vaut un Spark honnête sur données
  gonflées qu'un Spark cosmétique.
- **Risque « multi-agent gratuit ».** Le V3.1 pose lui-même « orchestré par défaut, agent par exception ». B1
  doit **prouver un gain** (trajectory eval, coût vs mono-agent), sinon c'est de la complexité pour la démo.
- **Risque scope-creep (le piège v1).** Gating strict §0 : rien ne démarre avant core déployé + spike vert.
  Un module bonus qui déborde se **coupe**, il ne repousse jamais la soumission.
- **Sécurité conservée.** Tout module touchant l'agent (B1) ou la donnée (B3) **hérite D1/D2/D5** ; aucun
  raccourci. B1 *compose* les garde-fous par worker — c'est un argument de plus, pas une dette.

---

## 5. COÛT ZÉRO — VÉRIFICATION PAR MODULE (extension de E.8)

| Module | Brique | Coût | Condition |
|---|---|---|---|
| B1 | LLM multi-agents | 0 € | même stack Groq free / Ollama ; caps par agent hérités E.4 ; budgets LiteLLM par caller |
| B2 | Spark | 0 € | PySpark local ; dataset synthétique généré localement ; aucun cluster managé |
| B3 | Kafka | 0 € | Redpanda en conteneur (Apache-2.0) ; profil compose opt-in |
| B4 | Warehouse cloud | 0 € | BigQuery free tier (1 To/mois) **ou** MotherDuck free ; Terraform CLI gratuit ; `destroy` après démo ; garde-fou cap requête |
| B4 | IaC | 0 € | Terraform open source ; state local (pas de backend payant) |
| B5 | Tracing/dashboard/drift | 0 € | Langfuse self-host · OpenTelemetry · Grafana · Evidently — tous OSS |
| B6 | Kubernetes | 0 € | kind local ; K8sGPT OSS (mode LLM local Ollama ou clé optionnelle jamais requise) |
| B7 | DataOps (Elementary, gates, alerting) | 0 € | package dbt Elementary OSS ; notifications GitHub Actions ; callbacks SLA Airflow — aucun SaaS d'observabilité payant |

Règle E.8 maintenue : **toute brique introduisant un coût = rejet automatique**, alternative gratuite ou
question à l'humain. Le free tier BigQuery/MotherDuck est plafonné et `terraform destroy` documenté pour ne
laisser aucune ressource facturable.

---

## 6. VERDICT

**V3.1 (core) : inchangé, prioritaire, à livrer d'abord.** V3.2 ne le fragilise pas — il attend qu'il soit vivant.

**V3.2 (bonus) : défendable et à fort ROI carrière, à deux conditions** — (1) gating strict (rien avant core
déployé + spike vert) ; (2) honnêteté d'échelle sur B2/B3 (données synthétiques + ADR, jamais de prétention de
nécessité). Fait dans cet ordre — **B1 → B5 → B2/B3 → B7 → B4 → (B6)** — il transforme Cyclebeat d'« un bon
capstone AI Dev Tools » en **portfolio DE/AE-avec-agentique-et-DataOps complet** : multi-agents supervisé et
évalué, batch distribué, streaming, data reliability engineering (gates bloquants + observabilité + runbook
incident), warehouse cloud + IaC, observabilité de production.

Rappel final (priorité zéro, inchangée depuis la première revue) : **le livrable qui vaut, ce n'est pas ce plan,
c'est le repo buildé.** V3.2 ne vaut rien tant que V3.1 n'est pas en ligne. Construis le core, soumets, déploie —
*puis* ouvre le bonus track.

---

## 7. EXPLORATOIRE — Mode Live par capture audio (hors-grille · décision reportée)

Ajouté le 2026-07-28. **Ce n'est pas un module bonus** (B1-B7 sont DE/portfolio) ; c'est une **idée
produit/DSP** dont le sort est explicitement indécis. Développé en détail dans `FUTURE_WORK.md` (racine).

**Idée.** Capter le son qui joue sur la machine (loopback système) et détecter tempo/beats en temps
réel, pour que le coaching marche avec **n'importe quelle** source (Spotify/YouTube/Deezer/fichier local)
— la source devient indifférente puisqu'on analyse le signal, pas un catalogue. Contourne tous les
problèmes de déprecation d'API et de licence.

**Pourquoi ce n'est pas le cœur.** (1) C'est **réactif, pas anticipatif** — un flux live n'expose que
le passé, donc la séance structurée et l'alerte −10 s cassent, sauf à ajouter une identification par
empreinte→métadonnée (Chromaprint/AcoustID → MusicBrainz/AcousticBrainz). (2) C'est **orthogonal à la
grille DE** : une app DSP temps réel jette dlt / lake / dbt / Airflow / copilot — précisément ce qui
donne le 30/30 et le pitch DE/AE.

**Stack (0 €) :** loopback (`pyaudiowpatch`/`soundcard` Win · BlackHole Mac · PulseAudio Linux) +
`aubio`/`madmom`/`BeatNet` ; Chromaprint/AcoustID en option.

**Trois options — à définir plus tard (préférence par défaut = 1) :**
1. **Feature future** (« mode Live ») ajoutée *après* la livraison du cœur DE — garde le 30/30 intact.
2. **Projet séparé** — un coach tempo temps réel, assumé comme DSP, pas comme DE.
3. **Pivot complet** — abandonner la grille DE/le plan pour en faire le projet principal ; seulement
   si l'objectif de carrière bascule vers le DSP/temps réel.

**Gating inchangé :** rien ne démarre avant que le cœur V3.1 soit déployé + le spike sources vert.

---

## ANNEXE — ADRs à produire pour V3.2

- `adr-b1-multi-agent-framework.md` — LangGraph vs superviseur framework-light ; quand un graph framework est légitime.
- `adr-b2-spark-scale-threshold.md` — DuckDB par défaut, Spark comme spike d'échelle ; seuil de volume ; données synthétiques.
- `adr-b3-batch-vs-streaming.md` — quand le streaming se justifie ; Redpanda vs Kafka.
- `adr-b4-cloud-warehouse.md` — DuckDB local vs BigQuery/MotherDuck ; IaC Terraform ; garde-fous coût free tier.
- `adr-b5-cross-model-judge.md` — pourquoi le juge doit différer du générateur.
- `adr-b6-k8s-optional.md` — pourquoi K8s est hors trajectoire cœur (à ne faire que si cible DevOps).
- `adr-b7-dataops.md` — couche data-reliability : gates bloquants, observabilité Elementary, alerting, runbook incident.

*Plan CycleBeat v3.2 — couche bonus — Ellie Pascaud — Juillet 2026.*
*Références : CYCLEBEAT_PLAN_V3.1.md (core, conservé), MAPPING_FORMATIONS_CYCLEBEAT.fr.md (angles morts & priorités).*
*Note : `docs/adr/` (ADR B1–B6) est en anglais — artefacts du repo, orientés portfolio.*

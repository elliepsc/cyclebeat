# CYCLEBEAT — ROADMAP CONSOLIDÉE

> **Note du 22 octobre 2026.** Le travail planifié vit dans les [issues GitHub](https://github.com/elliepsc/cyclebeat/issues)
> (jalons « Submission » et « Complete project ») ; la spécification est [product-spec.md](../product-spec.md).
> La liste `[présentable]` ci-dessous est une réserve, pas un plan : une ligne retenue devient une issue.
> Le reste de ce document n'est pas réécrit.

> Version : **R1.3 — clôture de la phase 1** (2026-08-15)
> *R1.1 :* grille 2026 (max 30 pts, MCP déplacé crit 2→12), mapping modules↔phases↔critères (§2.6), décision DB Postgres+DuckDB (§2.7), objectif pro « flotte d'agents » (§4.1).
> *R1.2 :* phase 1 synchronisée sur **ADR-005** (backbone = librosa sur preview Deezer ; Jamendo abandonné ; Spotify = import playlist optionnel via ISRC, hors core).
> *R1.3 :* **phase 1 CLOSE** — ADR-005 acté, ADR-004 superseded, rapport de spike chiffré finalisé, `extract_jamendo` retiré de `dag_ingest` (note datée en E.5) ; gate (b) remplie ; phase 2 débloquée.
> **Remplace conceptuellement** `CYCLEBEAT_PLAN_V3.md`, la strate « V3.1 » (durcissements D, jamais matérialisée en fichier) et `CYCLEBEAT_PLAN_V3.2.md`.
> Objectif : **une seule ligne de couches**, du livrable au bonus, avec un statut par phase — au lieu de trois plans parallèles.
> Les **contrats d'exécution normatifs** (Annexe E.0–E.8) restent la référence détaillée : ce document est la *colonne vertébrale*, pas un re-spec. Voir §8.

---

## Priorités et calendrier — état au 2 octobre 2026

### Légende
- `[rendu]` : nécessaire pour le rendu AI Dev Tools Zoomcamp 2026.
- `[présentable]` : solide et défendable en entretien, après le rendu.
- `[production]` : ce qu'il faudrait pour un vrai système. Sans date.

Règle de verdict : `[rendu]` complet = robuste pour le homework ; + `[présentable]` = solide et
présentable ; + `[production]` = prêt pour un vrai système.

### Calendrier
- Point de décision : **12 octobre 2026**. Si le frontend n'appelle pas l'API de bout en bout en
  local à cette date, bascule sur le filet du 17 novembre et replanifie.
- Application complète en ligne : au plus tard le **20 octobre** (URL vivante depuis au moins une
  semaine le jour du rendu).
- Gel : **25 octobre**. Rendu : **26 octobre au soir** (échéance le 27 à minuit).
  Filet : **17 novembre**.
- Au rendu : tag `v1.0-submission`, et c'est ce commit qui est soumis.

### `[rendu]`
| Livrable | État |
|---|---|
| Moteur, ingestion, dbt, DAGs, contrat OpenAPI, backend, CI | ✅ |
| README réécrit, `CONTRIBUTING.md`, contrôle des liens en CI | ✅ |
| Persistance : Postgres si `DATABASE_URL`, SQLite par défaut | ✅ |
| API déployée sur Render, base de démo construite dans l'image | ✅ |
| URL de l'API et documentation interactive (`/docs`) ajoutées au README | ✅ |
| Frontend minimal (phase 5) : client généré, 2 écrans, vitest, CORS, job CI | ✅ (PR #27 mergée ; test navigateur du propriétaire, voir `docs/ai-workflow.md`) |
| Frontend en ligne (https://cyclebeat-web.onrender.com) et déploiement automatique : GitHub Actions déploie sur `main` après CI verte (`autoDeployTrigger: off` + deploy hooks, `tools/deploy.py`) | ✅ — première exécution réelle verte sur `a50a137` (1 min 4 s) |
| `docker compose` complet et tests d'intégration | ✅ (PR #35 mergée ; sur `main`, `deploy` a tourné après `integration` : [run 38158175761](https://github.com/elliepsc/cyclebeat/actions/runs/38158175761)) |
| Outils en lecture seule sur les marts (`query_marts`, rapport qualité, file de revue), garde-fous E.4 sans LLM, tests d'injection au niveau SQL (§2.8) | ✅ (PR #38 mergée, démo PR #39) : `query_marts` et `get_quality_report`, 6 tests E.4 ([ADR-012](adr/adr-012-deterministic-tools-llm-separation.md)) ; `list_review_queue` coupé par la propriétaire |
| Critère 12 : serveur MCP réutilisant ces outils, skill `new-mart`, hook de pré-commit (tests et détection de secrets), notes de permissions (§2.8) | ✅ (PR #38 mergée, démo PR #39, [docs/demo.md](demo.md)) : le garde-fou livré est un hook PreToolUse et des règles deny ([docs/permissions.md](permissions.md)), pas un hook git de pré-commit ; il n'y a ni tests ni détection de secrets au commit |
| Critère 13 : audits de PR par le sous-agent `security-auditor`, Semgrep en CI, notes de sécurité agent, diagnostic opérationnel, politique IA (§2.8) | ✅ sur la branche `phase-10/security-audit` (PR à ouvrir par la propriétaire) : index [security/README.md](../security/README.md), diagnostic [ops/](../ops/README.md), Semgrep et gitleaks bloquants en CI (`make audit`). Le patch du hook qui répond à l'audit de #38 ([pr-38-hook.patch](../security/pr-audits/pr-38-hook.patch)) reste à appliquer par la propriétaire |
| Carte des critères de la grille vers les chemins du repo, pour les reviewers. Chaque chemin attendu par la grille existe soit comme vrai fichier (dont un `product-spec.md` court et réel), soit comme dossier avec un README de redirection (par exemple `backend/README.md` vers `api/` et `cyclebeat/`) | ⬜ |
| Test depuis un clone propre, gel, tag | ⬜ |

### `[présentable]`
| Livrable | État |
|---|---|
| **Montée de version de DuckDB (CVE-2024-41672), en tête des priorités après le rendu.** Mention C1 : avant la correction de `fix/query-marts-cte-scope`, `JOIN LATERAL sniff_csv('<fichier>')` passait la garde et renvoyait la première ligne d'un fichier par `query_marts`, y compris sur `main` (audit avant merge, passe 3) ; la garde est aujourd'hui la seule ligne qui l'arrête. Sur la 0.10.2 verrouillée, `sniff_csv` lit encore la ligne d'en-tête de n'importe quel fichier malgré `enable_external_access=false` (mesuré le 13 octobre 2026) ; la garde SQL de `query_marts` la refuse. Elle lit aussi sur la base d'exposition où tournent désormais les outils (`exposed()`). Les tests `test_the_locked_connection_refuses_sniff_csv` et `test_the_exposure_database_refuses_sniff_csv` (`xfail(strict=True)`) passeront au rouge après la montée : retirer alors les marqueurs. Revoir aussi la liste des fonctions refusées par nom (`_FORBIDDEN_FUNCTIONS`, `api/services/warehouse_tools.py`), mesurée sur la 0.10.2 : c'est une liste noire. Une macro définie dans l'entrepôt passerait (aucune aujourd'hui) ; à cette occasion, refuser toute fonction non interne (`duckdb_functions() WHERE NOT internal`) ou passer à une liste blanche de fonctions | ⬜ |
| Limite mémoire au niveau du processus des outils en lecture seule (`query_marts`, `get_quality_report`) : la vraie correction de NEW-M1. Les `range` / `generate_series` / `repeat` scalaires allouaient hors du `memory_limit` de DuckDB (1666 Mo RSS mesurés, processus tué au-delà) ; la garde les refuse en attendant. Couvrir aussi la copie des marts, qui se fait avant le verrouillage et hors du minuteur de 5 s | ⬜ |
| Requêtes refusées à tort par la garde des outils en lecture seule : `USING SAMPLE` (l'injection de `LIMIT 200` le place avant la clause et DuckDB refuse la requête), une jointure de tables nommées entre parenthèses (`FROM (a JOIN b ON …)`, refusée comme source), l'instruction `PIVOT` (refusée comme non-SELECT). Fonctionnel, pas de sécurité : relevé par les passes 3 et 4 de l'audit de `fix/query-marts-cte-scope` | ⬜ |
| Chemin Postgres testé en CI contre une vraie base (`test/postgres-ci`) | ✅ |
| Neon en production, seulement après le point précédent | ⬜ |
| ADR-010 : sources de morceaux et de BPM, conditions d'utilisation Deezer | ✅ |
| Aucun stockage durable d'audio : extrait analysé depuis un fichier temporaire supprimé (`fix/no-audio-cache`, ADR-010) | ✅ |
| Documentation à source unique (plans archivés, index des ADR) | ⬜ |
| Mesure de la justesse du BPM sur des pistes de référence (zone correcte, erreurs d'octave, calibration de la confiance). Cas observés en production le 2 octobre 2026 : « Ain't No Sunshine » à 161,5 BPM avec une confiance de 0,9 (erreur d'octave probable, recoupement validé à tort) ; « Blinding Lights » à 86,1 BPM (mi-tempo probable). Aucune correction dans le code à ce stade | ⬜ |
| Couche LLM du Warehouse Copilot : LiteLLM + Ollama, CoachingGenerator, évaluations du copilote, `fct_llm_calls` / `fct_agent_runs`, `trigger_resolve` avec ses 2 tests, boucle d'agent et caps de run (§2.8). Le contrat (`openapi.yaml`) devra alors lister les codes d'erreur des outils (`table_not_allowed`, `function_not_allowed`, `guard_error`, `internal_error`, …) et dire si un refus est un événement du flux SSE ou une erreur RFC 7807 (relevé par `contract-guardian`, passe 1) | ⬜ |
| Packaging du pack d'extension en plugin + `docs/agent-pack.md` ; Snyk et K8sGPT en phase 10 (§2.8) | 🟡 fait : plugin généré par `make plugin` (`plugins/cyclebeat-agent-pack/`), contrôle de dérive en CI, chargé par `--plugin-dir` dans la démo ([docs/demo.md](demo.md)) ; la doc est [docs/agent-extension-pack.md](agent-extension-pack.md). Reste : `version` et `author` absents de `plugin.json`, pas de marketplace ; Snyk et K8sGPT ⬜ (phase 10) |
| Écran de KPI qualité branché sur `/v1/quality/*` | ⬜ |
| Image en deux étapes (l'image de démo pèse 911 Mo : `build-essential` et le cache de build restent dans l'image finale), utilisateur non root (l'image tourne en root ; droits en écriture limités au dossier de la base SQLite) | ⬜ |
| GIF de démo, test depuis un clone propre par une autre personne | ⬜ |
| Récit d'entretien : décisions prises contre l'avis de l'agent | ⬜ |
| Marquer ou exclure les séances de test avant de brancher une base persistante (le test après déploiement crée une séance par déploiement) | ⬜ |
| Inclure `tools/` dans la vérification mypy (aujourd'hui limitée à `api/`) | ⬜ |
| `ruff format` n'est pas vérifié par `make lint` : `ruff format --check` signale 15 fichiers sur `api tests` (vu pendant la démo de la phase 7) et 28 sur tout le périmètre de `make lint` (mesuré le 12 octobre 2026) | ⬜ |
| Patch du hook (propriétaire, `agent-hooks/`) : refuser `gh issue reopen`, `gh issue delete`, `gh issue transfer` et les changements d'état d'une issue par `gh api` (appel non-GET sur `/issues/<N>` avec un champ `state`) ; la branche `gh issue edit --state` vise une option absente de gh 2.45 (à revoir contre le manuel). Ajouter la ligne « issues » au tableau « What the agent may not do » de `docs/permissions.md`. Relevé par `security-auditor` sur la branche de l'issue #45 (M1b, M1c, [triage](../security/pr-audits/pr-45-triage.md)). Deux faux positifs relevés pendant #57, à corriger dans le même patch : `ls -la data/*.db data/*.duckdb`, une lecture, refusé comme écriture (`writes to data/ and lake/ are refused (*.db)`) ; un motif de chemin lu dans le texte d'un message de commit (`git commit -m "… lake/raw/{tracks,resolutions}/dt=2026-07-29 …"`, refusé avec `(dt=2026-07-29,)`, commit fait par la propriétaire) | ⬜ |
| Base analytique absente : `readable()` (`api/repositories/warehouse.py`) retombe sur une connexion en écriture qui crée une base DuckDB vide, et l'API répond alors 422 `empty_catalogue` à la génération au lieu d'être signalée en mauvaise santé. Relevé en phase 8, non corrigé | ⬜ |
| Endpoint de disponibilité (readiness) qui vérifie les dépendances (un `select 1` sur la base transactionnelle, l'entrepôt analytique lisible) et répond 503 si l'une manque, déclaré dans `openapi.yaml` avec backend et client généré dans la même PR ; le healthcheck compose de `api` l'appelle au lieu de `/health`. Constat reproduit : Postgres arrêté, l'API reste `(healthy)` et `generate` répond 500 ([ops/incident-2026-10-15-postgres-down.md](../ops/incident-2026-10-15-postgres-down.md)). Même famille que la ligne précédente (`readable()`) : une sonde de vivacité tient lieu de sonde de disponibilité | ⬜ |
| Exposition locale d'Airflow : le profil `pipeline` publie le port 8080 sur toutes les interfaces de l'hôte (`docker-compose.yml:157`), et Airflow 3.0.6 porte 3 CVE critiques et 11 hautes (développement seulement, [security/scans/2026-10-20.md](../security/scans/2026-10-20.md)). Lier le port à `127.0.0.1` et monter Airflow | ⬜ |
| Montée des dépendances de production signalées par pip-audit (gitpython, sqlparse, starlette, urllib3 ; aucun chemin d'exploitation dans CycleBeat, mesuré le 20 octobre 2026), avec la remise à jour générale des dépendances | ⬜ |
| Marquer comme données non fiables les chaînes externes (`title`, `artist`, `preview_url`) renvoyées par les outils MCP, à décider avec `trigger_resolve` en phase 6 (audit de #38, L2) | ⬜ |
| Migrer les tests `accepted_values` de `dbt/models/` de la forme `values:` au premier niveau vers `arguments:`, dépréciée depuis dbt 1.11 (`MissingArgumentsPropertyInGenericTestDeprecation`, 18 occurrences mesurées par `dbt parse --no-partial-parse` le 23 octobre 2026, contre 11 avant #46, qui en a ajouté 7 pour suivre la convention du repo ; relevé par `dbt-reviewer`, finding 11) | ⬜ |
| Clé primaire sur la table `feedback` de la base transactionnelle (`api/repositories/database.py`) : elle n'a aucune identité, si bien que l'entrepôt ne peut dédoublonner un retour que par partition entière (#54). Changement d'API et de schéma, hors périmètre de #54 | ⬜ |
| Jeu de référence, tests de rapprochement et provenance des indicateurs : repris par [#60](https://github.com/elliepsc/cyclebeat/issues/60) | ✅ |
| Code v1 hérité dans `stg_feedback` : le filtre `session_id is not null or session_title is not null`, l'échelle `effort` (`Great`/`Okay`/`Hard`) et la part `session_title` de la clé de grain ne sont atteints par aucun chemin actuel. `feedback.session_id` est `NOT NULL` (`api/repositories/database.py`, `DDL_FEEDBACK`) et l'API n'accepte que `up`/`down` (`openapi.yaml`). Décider, dans une ADR, de retirer la branche v1 et l'échelle `effort`, ou de les garder pour un import de données historiques. Relevé pendant #60 | ⬜ |
| `_parse_ts` (`api/repositories/session.py`) remplace un `created_at` de plan illisible par l'heure courante, sans signal : même famille de repli silencieux que `_as_datetime`, corrigé côté pipeline par #57, mais côté API. Refuser la valeur, avec un code d'erreur déclaré dans `openapi.yaml`. Relevé pendant #57 | ⬜ |
| Colonnes `created_at` de la base transactionnelle en `TIMESTAMP` sans fuseau (`api/repositories/database.py`, `DDL_SESSIONS` et `DDL_FEEDBACK`) : la valeur stockée dépend du fuseau de la session Postgres, que #57 fixe à UTC à la connexion. Passer à `timestamptz`, avec une migration des lignes existantes. Relevé pendant #57 | ⬜ |
| `demo._stamp` (`cyclebeat/demo.py`) remplace un `generated_at` illisible du snapshot par une date fixe, sans signal. Repli déterministe, mais muet : refuser la valeur. Relevé pendant #57 | ⬜ |
| `save_patterns` (`db/runtime.py`) écrit une valeur par défaut au lieu de NULL quand un champ manque dans le fichier de patterns : `0.0` pour `bpm_range` (donc `bpm_mid = 0`), `0` pour `resistance`, `''` pour `effort`. Un 0 rend inopérants les contrôles de NULL ajoutés dans #55 (`bpm_bucket` et `resistance_bucket` à `unknown`, `check_invalid_pattern_buckets`) : une résistance à 0 est classée `light` sans être signalée ; une fenêtre BPM à 0 est classée `slow`, mais `check_pattern_bpm_range` la signale déjà. Écrire NULL. Relevé pendant #55 | ⬜ |
| Portée de la règle « pas de SQL hors de `api/repositories/` et `dbt/` » : elle vise le code applicatif (`CLAUDE.md`, #55), mais `db/runtime.py` (ingestion des patterns), `cyclebeat/lake.py` et `cyclebeat/warehouse.py` contiennent du SQL. Dire s'ils relèvent du code applicatif, et en conséquence les déplacer ou écrire l'exception dans `CLAUDE.md`. Relevé pendant #55 | ⬜ |
| Logique métier dans le staging : le mapping `effort` → `effort_bucket` est dans `stg_patterns`, alors que le staging doit rester 1:1 avec la source. Les `select *` de `stg_patterns.sql` et de la CTE `patterns` d'`int_pattern_effort_profile.sql` sont antérieurs à #55 ; #55 a ajouté son mapping au même endroit pour rester cohérent avec le code existant. Le déplacer vers `int_pattern_effort_profile` ne change aucun chiffre. Relevé par `dbt-reviewer` pendant #55 (N6) | ⬜ |

### `[production]` — sans date
- « Idée 2 » : lecteur YouTube intégré, table d'observations de BPM, tap tempo, micro, puis
  Spotify « en cours de lecture ». ADR à écrire après le rendu (lecture, identité, observations de
  BPM), après le tag `v1.0-submission`.
  - Séquences dans la chanson (ADR à écrire après le rendu, distinct de celui de l'idée 2 : règles
    de cadence et de résistance). Décisions de produit, à valider :
    - Chaque chanson est découpée en sections (intro, couplets, refrains, pont, fin). La première
      chanson de la séance est un échauffement calme.
    - Cadence de la section = BPM de la section × multiplicateur (1 ou ½), dans une plage de
      cadence sûre à valider.
    - Résistance inversement liée à la cadence (lent = plus lourd), amplitude ajustée selon le
      niveau.
    - Intensité interne de 1 à 10 par section, relative à une résistance de base choisie à
      l'échauffement. Affichage « niveau X » pour les vélos gradués, « ±¼ tour » pour les vélos
      à molette.
    - Sections obtenues par marquage manuel pendant l'écoute, puis par découpage automatique sur
      des fichiers personnels, mesuré contre les marquages manuels.
    - À valider avec la pratique ou un coach : plage de cadence, choix du multiplicateur,
      conversion niveau vers tours.
- Générateur de consignes par LLM, avec évaluations et coût par séance mesuré.
- Authentification, limitation de débit, gestion des secrets.
- Gates de qualité bloquants, alerting, runbook (B7).
- Infra as code et entrepôt cloud (B4).
- Tests de charge, agent de premier diagnostic en lecture seule.
- Licence musicale valable pour un usage réel.
- Bornes d'effort physique validées par une coach.

---

## 0. Pourquoi ce document (refonte du versioning)

Le versioning actuel est une des sources du désordre : trois plans parallèles (`V3`, `V3.1`, `V3.2`) au lieu d'une progression, dont **deux références de vérité pointent vers des fichiers absents** (`CYCLEBEAT_PLAN_V3.1.md` n'existe pas ; `CYCLEBEAT_PLAN_V2.md §6-9` non plus). On remplace cette pile par **deux couches linéaires** :

| Couche | Nom | Ce que c'était avant | Nature |
|---|---|---|---|
| **L0** | **CORE** | Plan V3 (§1–§18) + durcissements « V3.1 » (D1–D8) fondus dedans | **À livrer d'abord.** Non négociable. C'est le 30/30 de la grille + la sécurité/infra. |
| **L1** | **EXTENSIONS** | Plan V3.2 (bonus B1–B7) | **Gaté.** N'ajoute aucun point ; ajoute de la profondeur portfolio. Ne démarre qu'après L0 en ligne. |

Correspondance des fichiers hérités (aucun n'est supprimé ; ils sont désormais dans `docs/archive/` — voir §7) :

| Fichier hérité | Devient | Action recommandée |
|---|---|---|
| `CYCLEBEAT_PLAN_V3.md` | **Source de l'Annexe E** (contrats d'exécution) + corps L0 | Conserver **uniquement pour l'Annexe E.0–E.8** ; le reste est repris ici |
| « V3.1 » (D1–D8) | **Sous-section durcissements de L0** (§2.3) | Le fichier canonique n'a jamais existé — dette à clôturer (§7) |
| `CYCLEBEAT_PLAN_V3.2.md` | **Couche L1** (§4) | Conserver comme spec détaillée des modules B1–B7 |
| `CYCLEBEAT_PLAN_V3.2.fr.md`, `MAPPING_FORMATIONS_*` | Inchangés | Référence (mapping formations, blind spots) |
| `BACKLOG*.md`, `*_ultraplan.md`, `ROADMAP_V1/V2*`, `fitflow_*`, `chatgpt.md` | Archives V1/V2 | Candidats à `archive/` (hors périmètre de cette refonte) |

**Ordre des sources de vérité (repris de E.0, inchangé) :** (1) le code du repo tel qu'il est ; (2) l'Annexe E ; (3) ce document (colonne vertébrale L0/L1) ; (4) le corps du plan V3 pour le détail historique. En cas de conflit, la source la plus haute gagne **et on le signale**.

---

## 1. État actuel (snapshot vérifié — `origin/main` = `6da3e71`, 2026-08-21)

> **Note 2026-10-25** : instantané d'août 2026, l'état courant est dans la ligne de chaque phase (§2.1) et dans les [issues](https://github.com/elliepsc/cyclebeat/issues).

| Élément | État |
|---|---|
| **Gate L0 → L1** | 🔴 **FERMÉ** — (b) remplie, (a) et (c) non ; aucun module B ne peut démarrer |
| Phase 0 — Purge & setup | ✅ **DONE** (v1 purgé, hygiène secrets vérifiée, CI verte, ADR-001/002/003) — PR #3, #4 |
| Phase 1 — Spike sources | ✅ **DONE** — ADR-005 acté, ADR-004 superseded, rapport chiffré finalisé sur les 50 pistes mesurées, `extract_jamendo` retiré de E.5. **Aucun compte Jamendo créé.** |
| Phase 2 — Cœur DE | ✅ **DONE** — resolver + cross-validation, lake Parquet, DuckDB/dbt, 3 DAGs Airflow chaînés sur les assets du lake — PR #10, #12 |
| Phase 3 — Moteur | ✅ **DONE** — planner + evaluator déterministes, ADR-007, mutation check vert en CI — PR #11 |
| Phase 4 — Contrat + backend | ✅ **DONE** — `openapi.yaml` contract-first, API en couches, `fct_session` (ADR-008), `mart_bpm_coverage`, schemathesis + test de divergence en CI |
| Chore A1 — README V3 | 🟡 **EN PR** (`docs/readme-v3`) — README réécrit (v1 retiré), `CONTRIBUTING.md` (env. WSL + workflow PR), `tools/check_links.py` branché sur `make lint` / CI ; chiffres re-mesurés : 233 tests unitaires, 55 évals, 23 contrat, 51 dbt |
| Phase 4b — Persistance Postgres (ADR-009) | 🟡 **EN PR** (`phase-4/postgres-persistence`) — sessions et feedback dans Postgres si `DATABASE_URL`, SQLite sinon ; chemin Postgres non encore testé en CI contre une vraie base ; sessions de démo éphémères (ADR-003) |
| Phase 5 — Frontend | ✅ |
| Phase 9 — CI/CD & deploy | ✅ |
| Phases 6, 7, 8, 10, 11 | ⬜ **TODO** — rien démarré |
| Couche L1 (B1–B7) | 🔒 **GATÉE** |

**Ce que la phase 1 a tranché.** Elle s'est close par **une décision, pas par une mesure supplémentaire**. **ADR-005** (supersede ADR-004) fixe le backbone BPM = **`librosa` sur le preview Deezer de 30 s** (vraie musique mainstream, source de métadonnées = source de lecture), le champ `bpm` de Deezer en **enrichissement** et le CSV en socle manuel ; Jamendo/CC est abandonné. Ce chemin était **déjà mesuré** : **82 % de pistes exploitables** (41/50), avec un biais haussier documenté. Le prix accepté, chiffré : **`single_source` 0.6 domine à 54 %**, `cross_validated` 0.9 plafonne à 26 % — car il dépend du champ `bpm` de Deezer, présent sur **23,3 %** des sorties récentes contre **65 %** des classiques. 12 % des pistes restent sans BPM (exclues du planner). Détail : `docs/spikes/phase1-source-coverage.md`.

**Prochain blocage** : aucun. Les phases 2, 3 et 4 sont closes ; la phase 5 (frontend React/Vite/TS, client TypeScript **généré** depuis `openapi.yaml`) peut ouvrir — une branche, une PR (E.0).

---

## 2. COUCHE L0 — CORE (à livrer d'abord)

**Définition.** Un produit data end-to-end : pipeline DE observable et testé (Deezer/CSV → lake Parquet → DuckDB modélisé dbt), exposé par une API sous contrat (FastAPI contract-first), consommé par un frontend React, opéré par un **copilote warehouse** (agent tool-use borné), le tout construit avec un workflow AI engineering documenté. Cible : **30/30** de la grille AI Dev Tools + les durcissements sécurité/infra.

### 2.1 Phases (§15 du plan V3, statut à jour)

| Phase | Contenu | Critère de sortie (bloquant) | Statut |
|---|---|---|---|
| **0. Purge & setup** | Purge v1 (Spotify/Qdrant/LangGraph/Streamlit → `archive/v1`), hygiène secrets, CLAUDE.md/AGENTS.md, Makefile, CI squelette, ADR-001 | CI verte sur repo purgé ; aucun secret dans l'historique (vérifié) | ✅ DONE |
| **1. Spike sources** | Couverture Deezer + librosa-preview (déjà mesurée) ; décision backbone **ADR-005** (Deezer preview, Jamendo abandonné) | Rapport chiffré finalisé + ADR-005 acté + ADR-004 superseded | ✅ DONE |
| **2. Cœur DE** | Resolver + cross-validation, 3 DAGs Airflow (`dag_ingest` = `extract_deezer` + `extract_csv`, cf. E.5), lake, DuckDB, dbt (recyclé) | `make ingest && make dbt` à froid **et** 3 DAGs verts ; dbt tests verts ; distribution confidence mesurée | ✅ DONE |
| **3. Moteur** | Planner + evaluator + property-based + adversarial + **mutation check** ; règles de construction actées en **ADR-007** | Mutation check vert | ✅ DONE — `make eval` vert (55 tests) |
| **4. Contrat + backend** | `openapi.yaml` écrit à la main AVANT le backend, FastAPI en couches (routers→services→repositories), unit + schemathesis ; **ADR-008** (persistance) et `mart_bpm_coverage` | Contrat validé en CI ; tests verts | ✅ DONE — `make contract` vert (23 tests) |
| **5. Frontend** | React/Vite/TS, client généré, 2 écrans, vitest | `npm test` vert ; parcours complet local contre l'API | ✅ DONE — PR #27, test navigateur du propriétaire |
| **6. LLM & copilote** | LiteLLM + Ollama, CoachingGenerator, **Warehouse Copilot** + outils bornés + éval anti-injection, `fct_llm_calls`/`fct_agent_runs` | Évals coach + copilote vertes en CI (Ollama) ; coût/séance mesuré | 🟡 outils `[rendu]` en lecture seule faits avec la phase 7 (`query_marts`, `get_quality_report`, 6 tests E.4, [ADR-012](adr/adr-012-deterministic-tools-llm-separation.md)) ; `list_review_queue` coupé ; couche LLM ⬜ |
| **7. Extension pack** | skill `new-mart`, subagent `dbt-reviewer`, hooks, **serveur MCP** warehouse, packaging plugin | Chaque brique a servi ≥ 1 fois (preuve dans `ai-workflow.md`) | ✅ PR #38 mergée : serveur MCP en lecture seule, skill `new-mart`, hook PreToolUse et règles deny, plugin généré, notes de permissions ([docs/agent-extension-pack.md](agent-extension-pack.md)) ; démo de la propriétaire, PR #39 mergée ([docs/demo.md](demo.md)) |
| **8. Intégration & compose** | `tests/integration` contre compose complet (api + web + postgres ; sans LLM, voir « Résolu le 9 octobre 2026 » en §2.8) | `docker compose up` sur clone propre + suite intégration verte | ✅ — PR #35 ; sur `main` ([run 38158175761](https://github.com/elliepsc/cyclebeat/actions/runs/38158175761)), `integration` vert (17:05:25 → 17:06:52 UTC), puis `deploy` vert (17:06:57 → 17:08:06 UTC) |
| **9. CI/CD & deploy** | Pipeline complet + deploy Render auto sur main vert *(action humaine : secrets Render)* | URL publique vivante ; un push déclenche test→deploy | ✅ — première exécution réelle verte du job `deploy` sur `a50a137` (tests puis hooks puis `live` puis 4 vérifications). La suite d'intégration reste de la phase 8 |
| **10. Sécurité & audit** | PR-Agent, Semgrep/Snyk, `agent-security.md`, `ai-policy.md`, diagnostic ops | Les 5 artefacts du §13 committés | ✅ `[rendu]` sur `phase-10/security-audit` : audits de PR par `security-auditor` (PR-Agent écarté), Semgrep + gitleaks en CI, pip-audit et npm audit ponctuels ; Snyk et K8sGPT restent `[présentable]` |
| **11. README & démo** | README (✅ #47, PR #63 : schéma d'architecture sourcé, `backend/README.md`, bandeau de statut) ; captures (✅ #47 : formulaire, séance générée, notation et confirmation de l'envoi, faites par la propriétaire, liées depuis le README) ; finalisation `ai-workflow.md` (✅, entrée de clôture du jalon Submission) ; remise en cohérence de cette roadmap, relevée en phase 8 (✅ #47, a minima : §2.7 et §2.2 corrigés, §1 et §5 datés comme instantanés) : §1 et la vue linéaire §5 sont des instantanés d'août périmés, et §2.2 (« phase 7 pendant Module 3 ») contredit le mapping §2.6 (P7 ↔ M5) ; §2.7 annonce « free tier Neon en prod », alors que la production tourne en SQLite dans le conteneur (`DATABASE_URL` absente, constaté le 11 octobre 2026, note datée dans ADR-009) ; `[rendu]` couche sémantique dbt, relevée en phase 7 (✅ #46, PR #56) : `schema.yml` citait un test absent (`check_confidence_values.sql`) et 4 marts sur 8 n'y avaient aucune entrée ; compteurs NULL sur un historique vide dans `mart_session_kpis`, révélés par la démo de la phase 7 (✅ #46, PR #56, [docs/metrics.md](metrics.md)) ; un retour compté une fois par partition `dt` de `stg_feedback` (✅ #54, PR #58, test de bout en bout `tests/test_feedback_dedup.py`) | Audit à froid depuis un clone propre, par une session neuve (critère modifié le 25 octobre 2026, note ci-dessous) : fait, [docs/audit/cold-audit-2026-10-27.md](audit/cold-audit-2026-10-27.md) ; ses findings bloquants B1, B2 et P1 corrigés par la PR #67 (#65) | ✅ |

> **Note 2026-10-25 (décision de la propriétaire, issue #47)** : le critère de sortie de la phase 11 était « testé depuis un clone propre par quelqu'un d'autre ». Aucun agent ne peut le remplir : une session de l'agent n'est pas « quelqu'un d'autre ». Il devient « audit à froid depuis un clone propre, par une session neuve », une session qui n'a aucun contexte de celle qui a écrit le code. Le test par une autre personne n'est pas abandonné : un pair pourra le faire pendant la période de relecture.

> **Correction de numérotation** (souvent confondue) : le **Warehouse Copilot** — l'agent analytics borné (`query_marts`, garde-fous, tests d'injection) — est construit en **phase 6**. La « §9 » du plan désigne la *section 9* qui le décrit, pas la phase 9. **Phase 9 = déploiement.** Actions humaines : **phase 1** (comptes API du spike) et **phase 9** (secrets Render).

### 2.2 Séquençage au rythme du cours

Suivant le mapping du §2.6 : phases 0-1 pendant le Module 1 · phases 4-5 pendant le Module 2 · phases 8-9 pendant le Module 3 · phase 10 pendant le Module 4 · phase 7 pendant le Module 5 (corrigé le 25 octobre 2026, #47 : cette ligne plaçait la phase 7 pendant le Module 3). Le projet avance au fil du zoomcamp au lieu de tout garder pour la fin.

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
2. Mutation check **et** tests d'injection des outils en lecture seule, partagés par le serveur MCP et le futur copilote, verts en CI.
3. `docker compose up` + suite d'intégration testés depuis un clone propre **par quelqu'un d'autre**.
4. URL déployée vivante depuis **au moins une semaine** (pas un deploy de dernière minute).
5. `docs/ai-workflow.md` avec **≥ 3 sessions réelles** détaillées (pas une reconstitution).
6. Historique git purgé des `.env`, clés rotées (non négociable — c'est public).

### 2.6 Grille AI Dev Tools **2026** (max **30 pts**) — mapping modules ↔ phases ↔ critères

> **Note du 22 octobre 2026.** Cette section décrit l'**ancienne** grille (14 critères, 30 points),
> remplacée le 16 octobre 2026 dans le dépôt du cours (commits 3ef6f18 et 526d9c1) par la grille officielle
> actuelle : 12 critères, 24 points, seuil de 10, reprise mot pour mot dans [docs/grading-criteria.md](grading-criteria.md).
> L'ancienne est archivée ([docs/archive/grading-criteria-v1-2026-10-09.md](archive/grading-criteria-v1-2026-10-09.md)).
> Les deux, exigence par exigence, avec l'état actuel : [docs/quality-bar.md](quality-bar.md). Les numéros
> « critère 12 », « critère 13 » de ce document et du dépôt sont ceux de l'ancienne grille.

Le syllabus 2026 a **14 critères** (max **30 pts** : somme des maxima du brouillon officiel, `docs/archive/grading-criteria-v1-2026-10-09.md`). Deux nouveautés vs 2025, et elles tombent pile sur ce que L0 planifiait déjà :

- **Crit 12 — Agent Extension Pack (2 pts, nouveau).** MCP **sort du crit 2** (où il était en 2025) et devient sa propre note ici, avec 6 briques : project instructions + 1 workflow/skill + 1 subagent + 1 outil/serveur MCP + 1 hook/guardrail + notes de permissions.
- **Crit 13 — Security/Audit/DevOps (2 pts, nouveau).** 5 artefacts : PR audit + scan déterministe + notes sécurité agent + diagnostic opérationnel + policy outils/données IA.
- **Crit 2 allégé** : « AI-Assisted Development Workflow » (specs, context files, review, verification) — **ne réclame plus MCP**.

Le §16 du plan V3 est **déjà** mappé sur ces 14 critères ; son total est de 30 et le crit 2 est à alléger.

**Mapping modules du cours → phases L0 → critères :**

| Module cours | Contenu | Phase(s) L0 | Critères visés |
|---|---|---|---|
| **M1** — AI-Native Workflow | spec, AGENTS.md, backlog, rôles PM/SWE/QA, orchestration multi-agents | P0, P1 + `ai-workflow.md` continu | 2 |
| **M2** — Full-stack app | spec, frontend, OpenAPI, backend, DB, unit tests | P4, P5 | 1, 3, 4, 5, 6, 7 |
| **M3** — Test/containerize/deploy | intégration, conteneurs, DB multi-env, CI, deploy, CI/CD | P8, P9 | 8, 9, 10, 11, 14 |
| **M4** — DevOps & Observability | OTel, alerting, **agent first-responder read-only**, audit sécurité récurrent, inventaire permissions | P10 | 13 |
| **M5** — Coding Agent Capabilities | MCP, skills, plugins, hooks, subagents, custom agents | P7 | 12 |

**Discipline de profondeur.** M4 est le module qui déborde le plus (OTel/Loki/Tempo/Grafana complets) : livrer **le minimum qui max le crit 13** (les 5 artefacts), pas une plateforme d'observabilité. Tout le reste des modules est déjà borné par les livrables de phase.

**Alignement de structure (cheap, évite de perdre des points en peer review).** Les reviewers scannent des chemins précis. S'assurer que le repo expose : `product-spec.md`, `openapi.yaml`, `frontend/`, `backend/`, `docker-compose.yml`, `.github/workflows/`, `docs/`, `security/`, `ops/`, et si M5 : `agent-capabilities/`, `agent-hooks/`, `mcp-server/`, `docs/agent-extension-pack.md`, `docs/permissions.md`. Mapper les noms actuels (`dbt/`, `dags/`, `mcp/`, `.claude/`) ou ajouter des pointeurs. Les artefacts de sécurité vont dans `security/` et `ops/` à la racine (§2.8).

### 2.7 Base de données (crit 7 + Module 3) — **Postgres transactionnel + DuckDB analytique**

Le Module 3 enseigne SQLite → **Postgres** (store transactionnel de l'app). CycleBeat est sur **DuckDB**, qui est un entrepôt **analytique** (dbt/marts/copilote) — un rôle différent. Décision (Ellie ouverte à Postgres) : **ne pas remplacer, séparer les rôles** — c'est l'archi réaliste OLTP+OLAP et un bon récit d'entretien :

- **Postgres** = transactionnel : `sessions`, `feedback`, état app (écriture fiable, fin de l'actuel best-effort `try/except pass` — dette E.2 close par la même occasion). Colle au modèle mental du cours, crit 7 + crit 9 plus nets.
- **DuckDB** = entrepôt analytique : lake → DuckDB → dbt (staging→marts), copilote warehouse. **Le différenciateur DE, conservé.**
- Le pipeline ingère les données transactionnelles Postgres dans l'entrepôt pour l'analytique (`fct_session`, `mart_feedback_summary`).

Coût : +1-2 j, 2 stores. **Zéro € préservé** (Postgres en conteneur compose. En prod, ADR-009 prévoyait le **free tier Neon**, le free tier Postgres de Render étant limité dans le temps, ce qui casserait la condition §18 « URL déployée vivante depuis au moins une semaine ». Ce n'est pas ce qui tourne : la production stocke sessions et retours en SQLite dans le conteneur, `DATABASE_URL` absente, note datée du 11 octobre 2026 dans [ADR-009](adr/adr-009-postgres-transactional-duckdb-analytical.md) ; corrigé le 25 octobre 2026, #47). Alternative minimale si le temps manque : DuckDB-only avec multi-env documenté — **passe** le crit 7 (libellé 2026 générique), mais raconte une histoire moins propre. Reco : la séparation, puisque tu es ouverte.

> **Impact phases :** Postgres transactionnel s'ajoute en **phase 4** (backend/persistance) ; l'entrepôt DuckDB reste **phase 2**. **Formalisé par ADR-009** (2026-08-30), qui supersede ADR-008 — celui-ci avait placé sessions/feedback dans DuckDB, faute d'avoir lu cette section. Le durcissement « 2 fichiers DuckDB single-writer » (§2.3) ne concerne plus que l'analytique.

### 2.8 Phases 6, 7 et 10 — minimum pour la grille ou version complète

Chaque phase est découpée en un **minimum pour la grille** (`[rendu]`) et une **version complète**.
Règle de la version complète : `[rendu]` si elle tient avant le gel du **25 octobre**, sinon
`[présentable]`. **Arbitrage du 9 octobre 2026 (propriétaire)** : toutes les parties « version
complète » ci-dessous sont classées `[présentable]`.

**Sources.** Tableau des phases (§2.1), grille (§2.6), texte du brouillon de la grille
(`docs/archive/grading-criteria-v1-2026-10-09.md`), plan archivé (`docs/archive/CYCLEBEAT_PLAN_V3.md` :
§9, §10, §12, §13, §15, §16, §18, E.4), lignes `[rendu]` de ce document, et les arbitrages du propriétaire
du 9 octobre. Ce que ces sources ne disent pas est marqué **à définir**. Le plan ne chiffre que
l'ensemble (« 32-40 jours effectifs », §15) : **les efforts ci-dessous viennent de la relecture du
propriétaire, pas des sources.**

**État du dépôt le 9 octobre 2026 (vérifié).**
- Phase 6 : rien. Ni `litellm` ni `sqlglot` dans `pyproject.toml`, ni `test_copilot_guards.py`, ni
  `fct_llm_calls` / `fct_agent_runs` dans dbt.
- Phase 7 : `CLAUDE.md` et `AGENTS.md` existent, ainsi que 4 sous-agents (`dbt-reviewer`,
  `ai-workflow-scribe`, `security-auditor`, `contract-guardian`). Il n'y a ni skill, ni hook, ni
  serveur MCP, ni note de permissions, ni plugin.
- Phase 10 : rien (`security/` et `ops/` n'existent pas).

#### Phase 6 — Outils en lecture seule (minimum) et couche LLM (complète)

| | Minimum pour la grille — `[rendu]` | Version complète — `[présentable]` |
|---|---|---|
| **Éléments** | Une **bibliothèque d'outils en lecture seule sur les marts**, sans LLM :<br>• `query_marts`, rapport qualité, file de revue<br>• garde-fous E.4 qui ne dépendent pas d'un LLM : SELECT unique (sqlglot), liste de tables autorisées, `LIMIT 200`, délai de 5 s<br>• tests d'injection **au niveau SQL**, dans le même commit que les outils (E.4). Répartition des 9 tests de `test_copilot_guards.py` : voir « Décisions et points ouverts », point 1 | La couche LLM :<br>• LiteLLM + Ollama<br>• CoachingGenerator (RAG sur 3 passages, garde-fous, éval de fidélité sur 10 cas de référence, §9)<br>• évaluations du copilote (10 questions de référence comparées à un SQL indépendant, §9)<br>• `fct_llm_calls` et `fct_agent_runs`, coût par séance mesuré (§10)<br>• boucle d'agent et caps de run (6 appels d'outils, question ≤ 500 caractères, délai de 60 s, budget LiteLLM, E.4)<br>• `explain_track` et `trigger_resolve` (plafond de 10, `confirm=true`, journalisé) avec ses 2 tests<br>• durcissements D (§2.3) : sandbox DuckDB, confirmation hors du canal LLM, injection indirecte |
| **Effort estimé** (propriétaire) | Outils et serveur MCP ensemble : 2 à 3 jours (comptés avec la phase 7) | Couche LLM : 4 à 5 jours (hors rendu) |
| **Points de grille** | Aucun critère dédié au copilote dans le §16. Les outils sont le code de l'outil MCP (critère 12) et la cible des tests d'injection de `agent-security.md` (critère 13) | À définir (aucun point supplémentaire documenté). Voir « Décisions et points ouverts » |
| **Valeur en entretien** | Outils bornés en lecture seule, garde-fous testés, **partagés** par le serveur MCP et le futur copilote (§12 : « une seule implémentation, deux consommateurs ») | « Agent borné en lecture, transposable en entreprise » (§9) ; « comment gouvernes-tu tes usages LLM ? » : coût LLM requêtable en SQL (§10) |

#### Phase 7 — Pack d'extension d'agent (critère 12, 2 points)

| | Minimum pour la grille — `[rendu]` | Version complète — `[présentable]` |
|---|---|---|
| **Éléments** | Chaque brique utilisée au moins une fois (preuve dans `ai-workflow.md`) :<br>• instructions de projet : fait (`CLAUDE.md`, `AGENTS.md`)<br>• sous-agent : fait (4 existent)<br>• **serveur MCP** réutilisant les outils de la phase 6 (version complète de la brique MCP)<br>• skill `new-mart` : un mart dbt de bout en bout (modèle, `schema.yml`, tests, doc, endpoint)<br>• hook de pré-commit : tests et détection de secrets<br>• notes de permissions | • packaging en **plugin** installable + `docs/agent-pack.md` (permissions, périmètre, sécurité) (§12) |
| **Effort estimé** (propriétaire) | Serveur MCP : compté avec la phase 6. Skill, hook et permissions : 1 à 1,5 jour | À définir |
| **Points de grille** | 2 (critère 12, §16) | 0 de plus. Confirmé par le brouillon de la grille (`docs/archive/grading-criteria-v1-2026-10-09.md`, critère 12) : le plafond de 2 points demande instructions de projet, workflow réutilisable, sous-agent, outil ou serveur MCP, hook ou garde-fou, notes de permissions. Le plugin n'y figure pas |
| **Valeur en entretien** | « La symétrie copilote produit / MCP de développement est l'idée forte du projet » (§12), ici avec les outils partagés et un copilote futur | À définir |

Le hook du plan (§12) vérifiait aussi la divergence de `openapi.yaml` ; cette vérification n'est pas
dans la liste retenue (elle tourne déjà en CI via `make contract`).

#### Phase 10 — Sécurité, audit, DevOps (critère 13, 2 points)

| | Minimum pour la grille — `[rendu]` | Version complète — `[présentable]` |
|---|---|---|
| **Éléments** | Les 5 artefacts du critère 13 :<br>• **audits de PR produits par le sous-agent `security-auditor`**. PR-Agent est écarté : il demande un modèle LLM (clé d'API ou modèle local), soit une dépendance et une configuration de plus, et `security-auditor` produit déjà des audits de PR. Le nombre de rapports est à définir<br>• **Semgrep en CI**<br>• `security/agent-security.md` : surface d'attaque du serveur MCP et des outils en lecture seule, tests d'injection<br>• diagnostic d'un incident compose réel (dans `ops/`)<br>• `security/ai-policy.md` | • scan Snyk en plus de Semgrep (§13)<br>• K8sGPT sur un cluster kind jetable (optionnel dans le plan)<br>• hors périmètre : la pile OTel/Loki/Tempo/Grafana complète (« le minimum qui max le critère 13, pas une plateforme d'observabilité », §2.6) |
| **Effort estimé** (propriétaire) | 1,5 à 2 jours | À définir |
| **Points de grille** | 2 (critère 13, §16) | 0 de plus : les 5 artefacts atteignent déjà le plafond (§2.6). Confirmé par le brouillon de la grille (critère 13) |
| **Valeur en entretien** | À définir | À définir |

Dépendance : le diagnostic d'incident compose demande la phase 8 (`docker compose` complet).

**Emplacement des artefacts.** Ils vont dans `security/` et `ops/` **à la racine**, comme l'attend la grille
(contenu attendu du dépôt, `docs/archive/grading-criteria-v1-2026-10-09.md`), et non dans `docs/security/` comme le prévoyait le plan.
Répartition confirmée par le propriétaire le 9 octobre 2026 : `security/` contient `agent-security.md`,
`ai-policy.md`, les audits de PR dans `security/pr-audits/` et les rapports Semgrep dans `security/scans/` ;
`ops/` contient le diagnostic d'incident. Fait en phase 10 : `.claude/agents/security-auditor.md` écrit son rapport en
retour (plus de `docs/security/`, plus de PR-Agent, plus de Write ; a8d9830, puis 331677a).

#### Efforts du reste du chemin `[rendu]` (relecture du propriétaire, pas des sources)

| Bloc | Effort |
|---|---|
| Compose et intégration (phase 8) | 2 à 3 jours |
| Outils en lecture seule et serveur MCP (phases 6 et 7) | 2 à 3 jours |
| Skill, hook et permissions (phase 7) | 1 à 1,5 jour |
| Sécurité et audit (phase 10) | 1,5 à 2 jours |
| README, démo, relecture (phase 11) | 1 jour |
| **Total `[rendu]`** (somme des bornes ci-dessus) | **7,5 à 10,5 jours** |
| Couche LLM (phase 6, complète) | 4 à 5 jours, hors rendu |

#### Décisions et points ouverts

**Décidé par le propriétaire le 9 octobre 2026 :**
1. **Répartition des 9 tests de garde-fous (E.4).** Dans le `[rendu]`, les 6 tests qui ne passent pas
   par un LLM : `rejects_multi_statement`, `rejects_non_select`, `rejects_table_outside_allowlist`,
   `limit_injected_when_absent`, `legit_question_with_delete_word_passes` (adapté en SQL : un SELECT
   contenant « delete » n'est pas bloqué) et `rejects_prompt_injection_drop` (adapté en SQL : une
   instruction `DROP TABLE` est rejetée). Dans le `[présentable]`, les 3 qui demandent la boucle
   d'agent ou `trigger_resolve` : `max_tool_calls_cap`, `trigger_resolve_requires_confirm`,
   `trigger_resolve_caps_track_list`. Cette modification du contrat E.4 sera formalisée par un ADR,
   écrit dans la branche de la phase 6 au moment de coder les outils (séparation outils / LLM,
   adaptation des deux tests).
2. **Hook** : la vérification de divergence d'`openapi.yaml` du plan n'est pas reprise ; ce contrôle
   reste en CI.
3. **PR-Agent** : écarté (voir la phase 10).

**Résolu le 9 octobre 2026, d'après le brouillon de la grille (`docs/archive/grading-criteria-v1-2026-10-09.md`).** Critères 8, 9
et 14 : le plafond de 2 points se juge sans la couche LLM. Le §16 du plan les reliait à `litellm` et
`ollama`, mais le texte de la grille ne les cite pas :
- **Critère 8, conteneurisation** : « The full system runs via Docker or Docker Compose with clear
  instructions ». Aucun service précis n'est exigé.
- **Critère 9, tests d'intégration** : « clearly separated, cover key workflows, and documented ». Les
  parcours clés suffisent (générer, relire, noter une séance ; qualité). Le parcours `copilot/ask` n'est pas
  exigé.
- **Critère 14, reproductibilité** : « Clear instructions exist to set up, run, test, and deploy the system
  end to end ». La démo sans clé n'y est pas citée ; `DEMO_MODE` par défaut la fournit déjà.

Réserve : c'est un **brouillon** (la page le dit : règles et notation peuvent changer). Relire la source
avant le gel du 25 octobre.

**Corrigé le 9 octobre 2026 :** le maximum de la grille est de **30 points** (somme des maxima du texte du
brouillon : 2 + 2 + 2 + 3 + 2 + 3 + 2 + 2 + 2 + 2 + 2 + 2 + 2 + 2). La §2.6 et les mentions de 32 points de
cette roadmap sont corrigées.

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

> **Note 2026-10-25** : instantané d'août 2026, l'état courant est dans la ligne de chaque phase (§2.1) et dans les [issues](https://github.com/elliepsc/cyclebeat/issues).

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
| 3 | **Conflit de langue** | E.6 dit « docs en français » ; CLAUDE.md dit « repo docs in English ». Non tranché — ce document est en FR (archives bilingues tolérées) |
| 4 | **Branches mergées non balayées** | `chore/dev-env-setup`, `docs/session-2026-07-sync`, `phase-1/source-spike`, `docs/status-2026-07-29` = `0` commit hors main → suppressibles ; `archive/v1-llm-zoomcamp` = `0` aussi mais **à ne JAMAIS supprimer** |
| 5 | **Entrées `ai-workflow.md` manquantes** (PR #6, #7) | Critère 2 de la grille — le plus souvent perdu en étant écrit après coup |
| 6 | **Drift contrat E.2 ↔ code** (chaîne `feedback`) | `raw.feedback → … → mart_feedback_summary` existe en dbt mais pas dans E.2 ; écriture DuckDB best-effort à fiabiliser ; exposer `mart_feedback_summary` sur l'allowlist du copilote |

---

## 8. Annexe E — contrats d'exécution (normatifs, par référence)

Les contrats normatifs **ne sont pas dupliqués ici** pour éviter le drift : ils restent l'Annexe E.0–E.8 du plan V3 (`docs/archive/CYCLEBEAT_PLAN_V3.md`, lignes 352→577). Ils couvrent :

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

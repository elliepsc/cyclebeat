# Data Agents Kit — 4 agents (+1 optionnel) pour DA / DE / AE

Kit de démarrage : définitions d'agents Claude Code + skill de contexte partagé.

## Architecture

| Agent | Rôle | Écrit quoi | Warehouse | Déclencheur |
|---|---|---|---|---|
| **librarian** | Doc, catalogue, glossaire, lineage, dark data | Métadonnées / doc (PR) | read-only | Post-merge / cron |
| **builder** | Dev dbt/SQL/pipelines sur ticket | Code (PR uniquement) | read-only prod, écriture dev | À la demande / label sur issue |
| **sentinel** | Observabilité, incidents, coûts | Diagnostics, PRs whitelist | read-only | Cron / alerte |
| **analyst** | Questions métier via semantic layer / marts | Rien (rapports) | read-only | À la demande |
| **steward** *(optionnel)* | Audit conformité / PII / accès | Rapports uniquement | read-only | Cron hebdo — contextes régulés seulement |

Principes non négociables :
1. **Aucun agent n'écrit en prod.** Tout changement passe par PR + CI + merge humain.
2. **Un agent ne surveille pas un agent** : le monitoring des agents est du code
   déterministe (CI, heartbeats, budgets, quotas de PRs) + ta revue hebdo.
3. **Pas de boucle fermée** anomalie → fix auto : Sentinel classe la cause,
   l'humain décide, Builder exécute. Exception : whitelist explicite + disjoncteur
   (même fix 3x/semaine = stop + escalade).
4. **Le skill de contexte est partagé** par tous les agents. Sa qualité fait 90 %
   de la leur.

## Ce qui n'est PAS un agent (volontairement)

- Backup/recovery, réplication, ingestion, orchestration → code déterministe.
- MDM, data contracts, architecture, définitions métier → décisions humaines
  (les agents implémentent et signalent, ne décident pas).
- Gouvernance courante → scripts + revue humaine ; Steward seulement si régulé.

## Installation

1. Copier le contenu de `repo-template/` à la racine de votre repo dbt
   (CLAUDE.md, AGENTS.md et tout le dossier `.claude/`).
2. Voir `INTEGRATION.md` pour le détail du placement et de l'interaction
   avec Claude Code / Codex.
3. **Remplir `.claude/skills/analytics-engineer/references/`** (warehouse, metrics, conventions, pitfalls) —
   étape la plus importante, faites-la en atelier d'équipe.
4. Créer les comptes warehouse dédiés : `agent_ro` (read-only) et `agent_dev`
   (écriture sur schémas dev uniquement).

## Ordre de déploiement recommandé

1. **Semaines 1-2** : remplir le skill de contexte. Rien d'autre.
2. **Semaine 3+** : Builder en manuel (tu l'invoques, tu reviews chaque PR).
   C'est la phase de remplissage accéléré de pitfalls.md.
3. Ensuite : Librarian en post-merge, puis Sentinel en diagnostic seul
   (aucun fix auto), puis Analyst quand metrics.md / semantic layer tient debout.
4. L'autonomie (whitelist Sentinel, merge auto) se gagne sur track record,
   jamais par anticipation.

## Métriques de pilotage (revue hebdo, 15 min)

- % de PRs agent mergées sans modification humaine (proxy de la qualité du contexte)
- Incidents causés vs résolus par les agents
- Coût compute par tâche agent
- Taux d'escalade de Sentinel (trop haut = seuils à revoir ; trop bas = méfiance)

## Kill switch

Désactiver le label GitHub / le cron suffit. Vérifier que c'est documenté et
testé avant le premier déploiement.

# Journal du workflow IA

## Session 2026-07-27 — Phase transverse — Commit des artefacts agents et ADR

**Boucle** : context → audit working tree → edit → diff → commit → push
**Outil/modèle** : Codex / GPT-5
**Prompt initial** : « commit et push »
**Itérations notables** : le repo était sur `main` avec des fichiers non suivis ; application de la règle projet "pas de commit direct sur main" en créant une branche dédiée avant push.
**Corrigé par la review humaine** : fichiers déjà présents dans le working tree avant intervention ; aucune correction humaine supplémentaire dans cette session.
**Partage des rôles** : écrit main humaine : artefacts agents, kit data-agents, ADR bonus / délégué : vérification Git, exclusion de `dbt/.user.yml`, création du journal, commit et push.
**Vérification** : scan regex secrets sur les fichiers ajoutés ; `dbt/.user.yml` identifié comme fichier local non committé. `make lint` tenté, bloqué car `make` n'est pas disponible dans le shell Windows courant.
**Leçon** : même pour un simple commit, vérifier les fichiers locaux évite de publier un identifiant utilisateur dbt.
**À capitaliser dans CLAUDE.md** : ajouter explicitement `dbt/.user.yml` aux fichiers locaux à ne pas committer.

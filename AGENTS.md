# AGENTS.md — CycleBeat (Codex / autres agents)

La référence est **`CLAUDE.md`** à la racine — lis-le en entier et applique-le.
Ce fichier n'est qu'un pointeur (Codex lit AGENTS.md) : ne jamais forker les règles.

Rappels non négociables si CLAUDE.md est inaccessible :
1. Sources de vérité : code du repo > Annexe E du plan V3 > plan V3 > plan V2 §6-9.
2. Rien d'inventé : ambiguïté → question ou 2 options chiffrées.
3. Une phase = une branche + une PR ; DoD = `make lint && make test-unit && make dbt` verts.
4. Interdits : secrets/.env ; openapi.yaml modifié sans backend+front dans la même PR ;
   SQL hors repositories/ et dbt/ ; dépendance non justifiée ; brique payante (coût zéro).
5. Formules E.2 (confidence, normalisation BPM, zones) : normatives, aucune variante.
6. Chaque session se termine par une entrée dans docs/ai-workflow.md.

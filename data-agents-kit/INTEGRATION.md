# Guide d'intégration — CLAUDE.md, agents, commands & Codex

## Où placer quoi

Copier le contenu de `repo-template/` à la racine de votre repo dbt :

```
mon-repo-dbt/
├── CLAUDE.md                  ← racine, COMMITTÉ. Chargé automatiquement par
│                                Claude Code à chaque session dans ce repo.
├── AGENTS.md                  ← équivalent pour Codex (et standard émergent
│                                multi-agents). Pointeur vers CLAUDE.md.
├── .claude/
│   ├── settings.json          ← permissions (deny/ask), committé = partagé équipe
│   ├── agents/                ← subagents : builder, sentinel, analyst,
│   │                            librarian, steward
│   ├── commands/              ← slash commands : /audit-codebase,
│   │                            /setup-guardrails
│   └── skills/
│       └── analytics-engineer/ ← contexte tribal (metrics, pitfalls,
│                                 conventions, warehouse)
├── models/ ...                ← votre projet dbt habituel
```

## Comment chaque pièce est chargée (Claude Code)

| Fichier | Chargement | Coût contexte | Usage |
|---|---|---|---|
| `CLAUDE.md` (racine) | **Automatique, chaque session** | Permanent → le garder dense et normatif | Règles de comportement |
| `~/.claude/CLAUDE.md` | Automatique, toutes sessions | Vos préférences perso (pas committé) | Style personnel |
| `CLAUDE.md` de sous-dossier | Quand Claude travaille dans ce dossier | Contexte local (ex. `models/marts/finance/`) | Règles spécifiques domaine |
| `.claude/commands/*.md` | **À la demande** via `/nom-commande` | Zéro tant que non invoqué | Workflows ponctuels |
| `.claude/agents/*.md` | Quand le subagent est invoqué (auto selon description, ou explicitement) | Contexte isolé par agent | Rôles + permissions |
| `.claude/skills/*/SKILL.md` | À la demande quand pertinent | Zéro tant que non chargé | Savoir volumineux |
| `.claude/settings.json` | Toujours appliqué | — | Garde-fous techniques |

Règle de tri — c'est le cœur de ta question « on glisse tout dans .claude ? » :

- **Comportement permanent** (contracts, tests, style SQL, règles agents) → `CLAUDE.md`.
  Il est chargé à CHAQUE session : chaque ligne coûte du contexte en continu.
- **Workflow ponctuel** (audit, setup guardrails, review) → `.claude/commands/`.
  C'est pourquoi vos fichiers CODEBASE_REVIEW_PROMPT et GUARDRAILS_DETECTION_SETUP
  ne vont PAS dans CLAUDE.md : les mettre en permanent gaspillerait du contexte
  et diluerait les règles. Ils deviennent `/audit-codebase` et `/setup-guardrails`.
- **Savoir volumineux et évolutif** (définitions métier, pièges) → skill/references,
  chargé au besoin et référencé depuis CLAUDE.md (§0).
- **Rôle avec périmètre d'outils propre** → `.claude/agents/`.

Astuce : CLAUDE.md supporte les imports `@chemin/fichier.md` si vous voulez
éclater les sections tout en gardant un chargement automatique.

## Utilisation au quotidien

```
# audit ponctuel
/audit-codebase                      # ou : /audit-codebase models/marts/

# installer les garde-fous manquants
/setup-guardrails

# invoquer un agent explicitement
> Utilise le subagent builder : ajoute la dimension canal à fct_orders (ticket DATA-123)

# les agents se déclenchent aussi automatiquement selon leur champ `description`
```

## Et Codex ?

- Codex lit **`AGENTS.md`** (racine + hiérarchique), pas CLAUDE.md.
  On garde CLAUDE.md comme source de vérité unique et AGENTS.md en pointeur
  avec un résumé de secours — ne jamais forker les règles en deux fichiers.
- Codex n'a ni subagents ni slash commands équivalents : les prompts
  réutilisables vont dans `~/.codex/prompts/` (copier audit-codebase.md
  et setup-guardrails.md si vous utilisez Codex).
- Conséquence importante : tout garde-fou critique doit vivre dans la CI
  (pre-commit, branch protection, tests, deny IAM), pas dans le fichier
  d'instructions. Un fichier d'instructions est un contrat moral ;
  la CI est un contrat exécutoire. Votre GUARDRAILS_DETECTION_SETUP
  est donc PLUS important que n'importe quel CLAUDE.md.

## Checklist d'installation (30 min hors remplissage du contexte)

1. Copier `repo-template/*` à la racine du repo (y compris `.claude/`).
2. Committer via une PR — CLAUDE.md se review comme du code.
3. Remplir `.claude/skills/analytics-engineer/references/` (atelier équipe —
   c'est l'étape qui fait 90 % de la valeur).
4. Adapter `settings.json` à votre stack (deny/ask).
5. Lancer `/setup-guardrails` → matrice de détection → implémenter le Tier 0.
6. Lancer `/audit-codebase` une première fois pour l'état des lieux.
7. Créer les comptes warehouse `agent_ro` / `agent_dev` avant d'activer
   les subagents.

## Ce qui a été modifié vs vos fichiers uploadés

- `CLAUDE.md` : contenu conservé intégralement, 3 ajouts —
  §0 Project Context (lien vers le savoir tribal), §21 Reverse ETL & Activation,
  §22 Operating Rules for AI Agents (PR-only, whitelist + disjoncteur,
  state-aware builds, kill switch, capitalisation du feedback).
- `CODEBASE_REVIEW_PROMPT.md` → `.claude/commands/audit-codebase.md`
  (+ frontmatter, + $ARGUMENTS pour scoper).
- `GUARDRAILS_DETECTION_SETUP.md` → `.claude/commands/setup-guardrails.md`
  (+ règle : détection présentée AVANT toute implémentation).

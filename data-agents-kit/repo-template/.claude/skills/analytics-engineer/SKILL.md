---
name: analytics-engineer
description: Contexte data de l'entreprise - warehouse, conventions dbt, définitions métier officielles et pièges connus. À charger avant TOUT travail sur les données. Partagé par les agents builder, sentinel, analyst, librarian et steward.
---

# Skill de contexte — Analytics Engineering

Ce skill est le socle commun des agents. Sa valeur dépend à 90 % de la qualité
des fichiers references/ — c'est le savoir tribal de l'équipe, à entretenir en
continu (voir la boucle de capitalisation de l'agent Librarian).

## Workflow imposé

1. **Avant tout SQL** : vérifier la définition dans `references/metrics.md`.
   Absente ou ambiguë → demander, jamais inventer.
2. **Pendant le développement** : appliquer `references/conventions.md` ;
   consulter `references/warehouse.md` pour les tables et leurs grains ;
   consulter `references/pitfalls.md` pour les pièges connus.
3. **Avant de livrer** : auto-review — grain, fan-out, ordre de grandeur,
   timezone, cas limites listés dans pitfalls.md.
4. **En restituant** : distinguer observé / interprété / supposé / incertain.

## Fichiers

- `references/warehouse.md` — stack, schémas, tables clés, grains, SLA
- `references/metrics.md` — définitions métier officielles (source de vérité)
- `references/conventions.md` — naming, structure, style SQL, tests
- `references/pitfalls.md` — pièges connus, à enrichir à chaque incident

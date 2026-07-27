# Conventions du projet

## Structure dbt
- `staging/` : stg_<source>__<table>. 1:1 avec la source. Renommage, cast,
  filtrage des lignes supprimées. Aucune logique métier. Matérialisation : view.
- `intermediate/` : int_<domaine>__<verbe>. Logique complexe réutilisable.
- `marts/` : fct_<processus> (événements mesurables), dim_<entité> (attributs).
  `marts/exports/` : modèles reverse ETL, légers, sans logique métier.

## Naming
- snake_case partout. Clés : <entité>_id. Booléens : is_/has_.
- Dates : <événement>_at (timestamp UTC), <événement>_date (date locale, préciser TZ).

## Style SQL
- CTEs nommées par intention, pas de subqueries imbriquées.
- Import CTEs en tête (select from ref()), logique ensuite, select final simple.
- Jamais de SELECT * hors import CTE. Jointures explicites (inner/left), jamais de virgule.

## Tests minimum par modèle
- unique + not_null sur la clé du grain.
- relationships sur les FK vers les dimensions.
- accepted_values sur les statuts / enums.

## PR & review
- Une PR = un objectif. Tests verts en CI obligatoires. Impact aval déclaré.
- Breaking change sur modèle exposé = version, jamais de modification en place.

# Warehouse & stack

> À REMPLIR — chaque section vide est un trou dans la mémoire de vos agents.

## Stack
- Warehouse : <!-- ex. BigQuery / Snowflake / Databricks -->
- Transformation : <!-- ex. dbt Core 1.x, repo git@... -->
- Orchestration : <!-- ex. Airflow / Dagster / dbt Cloud, fréquence des runs -->
- Ingestion : <!-- ex. Fivetran, CDC sur la base applicative (lag toléré : X min) -->
- BI : <!-- ex. Looker / Metabase / Power BI -->

## Schémas et environnements
- prod : <!-- schémas, qui écrit quoi -->
- dev / CI : <!-- convention dev_<user>_<schema> -->
- Accès agents : <!-- ex. rôle agent_ro (read-only prod), agent_dev (écriture dev) -->

## Tables clés (top 10-20)
| Table | Grain | Volumétrie | Partition / cluster | SLA fraîcheur | Notes |
|---|---|---|---|---|---|
| fct_orders | 1 ligne / commande | | date_order | 8h00 | |
| dim_customers | 1 ligne / client | | | 8h00 | |

## Sources amont
| Source | Mode (batch/CDC) | Fréquence | Contact équipe | Fiabilité connue |
|---|---|---|---|---|

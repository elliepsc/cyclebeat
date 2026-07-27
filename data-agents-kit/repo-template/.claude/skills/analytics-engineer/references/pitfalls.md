# Pièges connus

> Le fichier le plus rentable du projet. Chaque incident, chaque correction
> humaine réutilisable finit ici. Format : symptôme → cause → réflexe.

## Exemples à remplacer par les vôtres

### Doublons dans <source X>
- Symptôme : count > count distinct sur order_id certains jours.
- Cause : l'outil d'ingestion rejoue les webhooks en cas de retry amont.
- Réflexe : dédupliquer en staging par (order_id, updated_at desc).

### Timezone
- Les timestamps sources sont en UTC ; le métier raisonne en Europe/Paris.
- Réflexe : conversion en staging, jamais dans les dashboards.

### Table <Y> à ne pas utiliser
- legacy_customers existe encore mais n'est plus alimentée depuis 2025-03.
- Réflexe : toujours dim_customers.

### Job flaky connu
- <job> échoue ~1x/semaine sur timeout source ; une relance suffit.
- Réflexe Sentinel : relance auto autorisée (whitelist), 3 échecs consécutifs = escalade.

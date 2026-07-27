# Définitions métier officielles

> Source de vérité unique. Une métrique absente d'ici n'existe pas :
> on demande au métier, on tranche, on l'ajoute — on n'invente jamais.

## Format d'une entrée
### <Nom de la métrique>
- **Définition** : <!-- en une phrase, en langage métier -->
- **Formule** : <!-- SQL ou pseudo-formule exacte -->
- **Grain / périmètre** : <!-- inclusions, exclusions (tests internes ? annulés ?) -->
- **Owner métier** : <!-- qui tranche en cas de doute -->
- **Pièges** : <!-- ex. net de remises, hors taxes, timezone Europe/Paris -->

## Exemples à remplacer
### Chiffre d'affaires (CA net)
- Définition : somme des montants des commandes livrées, net de remises, HT.
- Formule : sum(amount_ht - discount_ht) where status = 'delivered'
- Périmètre : hors commandes de test (is_internal = false), hors annulées.
- Owner : Finance.
- Pièges : le champ amount de la source inclut la TVA — toujours partir de amount_ht.

### Client actif
- Définition : client avec ≥ 1 commande livrée sur les 90 derniers jours glissants.
- Owner : Marketing.
- Pièges : « actif » ≠ « inscrit » ; le CRM utilise 12 mois, définition NON officielle.

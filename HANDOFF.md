# Passation — RACE//RADAR

Dernière mise à jour : 22 novembre 2026, Europe/Paris.

## État vérifié

La version principale est publiée sur https://thomasnast2-glitch.github.io/race-radar/. Les tests GitHub, la dernière publication Pages et le dernier passage IFTTT ont réussi. Les données servies ont été relues après publication : aucun des six meetings hors périmètre, sept fiches vérifiées auprès des organisateurs, zéro conflit de dates en attente. Le semi-marathon de Colmar affiche 21,1 km séparément du 10 km et du marathon.

- Corrections principales : https://github.com/thomasnast2-glitch/race-radar/pull/2
- Réparation des distances héritées : https://github.com/thomasnast2-glitch/race-radar/pull/3
- Dernière recette complète : https://github.com/thomasnast2-glitch/race-radar/actions/runs/45013270373
- Publication vérifiée : https://github.com/thomasnast2-glitch/race-radar/actions/runs/45013448934
- Notifications : https://github.com/thomasnast2-glitch/race-radar/actions/runs/45013519635

## Ce qui a été fait et pourquoi

1. Récupération des sources et de l'historique du dépôt existant dans le dossier local du projet, auparavant vide, afin de reprendre le bon système. La branche locale main suit origin/main ; les versions de travail précédentes restent disponibles dans l'historique.
2. Exclusion des meetings de perche, lancers et salle classés à tort Cross ; six anciennes fiches sont archivées dans excluded_events.json. Objectif : conserver un calendrier running/trail/cross cohérent.
3. Correction de l'indicateur Running et des compteurs : les collectes dégradées et les conflits de dates restent visibles même si le workflow ou la veille des liens réussit. Un rapport sans source accessible n'est plus considéré sain.
4. Résolution des cinq conflits à partir des organisateurs : Grand Ballon sur deux jours, courses de Molsheim séparées par date et distance, Celtes et Pèlerins conservés comme deux courses distinctes. Les IDs existants sont conservés pour les favoris et la mémoire des alertes.
5. Ajout d'official_events.json, réappliqué avant les imports secondaires pour protéger les dates et distances vérifiées. La fiche du Grand Ballon précise les distances par jour.
6. Réparation des distances d'anciens regroupements : un format nommé explicitement, comme un semi-marathon, récupère sa liste propre au lieu de conserver les distances des autres formats.
7. Vérifications : 20 passages Python sous tests/, 16 passages Python racine, 10 tests JavaScript et 6 tests navigateur. Certains tests Python sont communs aux deux emplacements. Les envois sont simulés dans les tests ; les workflows réels ont ensuite été suivis jusqu'au succès.

## Ce qui reste à faire

- Rétablir une couverture FFA complémentaire si une source exploitable et autorisée est disponible. La collecte mensuelle ne découvre pas de lien exploitable ; la sonde saisonnière est bloquée par robots.txt. Ces limites sont affichées et ne doivent pas être masquées.
- Recontrôler périodiquement les pages organisateurs référencées dans official_events.json : ce registre contient des vérifications datées, pas une garantie que l'organisateur ne changera jamais son programme.
- Lorsqu'une course paraît suspecte, vérifier le format exact, la ville, la date et la source avant correction. Conserver les identifiants lorsque l'événement reste le même.
- Conserver une note de passation à jour à chaque fin de session : travail réalisé, motivation, prochaines étapes et incertitudes.

## Points incertains et limites

- La couverture des calendriers n'est pas exhaustive ; 4 contrôles de collecte sur 6 étaient disponibles lors du dernier contrôle, avec 2/2 sources de veille des liens accessibles.
- Les dates issues de calendriers secondaires ne constituent pas toutes une confirmation de l'organisateur. Une date de course ne prouve jamais une inscription disponible ; HYROX exige une validation officielle de la catégorie exacte, notamment Doubles Pro.
- Le succès du workflow IFTTT prouve son exécution, pas la réception sur le téléphone. Une coupure après réception du webhook peut empêcher une garantie d'envoi exactement une fois.
- Les fichiers YAML à la racine sont historiques. Les workflows actifs sont uniquement sous .github/workflows/.

## Reprise technique

Lire README.md et ce fichier, actualiser main sans écraser de modifications locales, examiner les dernières exécutions et reproduire le défaut avant modification. Utiliser les tests existants et compléter uniquement les scénarios de régression nécessaires. Après publication, attendre les workflows puis relire les données du site. Éviter toute intervention simultanée de deux agents sur les mêmes fichiers. Ne pas exposer ni remplacer les secrets ou les destinataires de notifications.

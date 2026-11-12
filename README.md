# RACE//RADAR

Agenda Running, Trail, HYROX et Cyclo : https://thomasnast2-glitch.github.io/race-radar/

## Synchronisations

Les workflows actifs se trouvent dans `.github/workflows/`.
Running collecte les calendriers, Cyclo surveille les organisateurs et HYROX relève des pistes de presse.
Le tableau « État du radar » présente les dates des rapports et les dernières exécutions GitHub.
Un contrôle de source réussi ne garantit pas la disponibilité des inscriptions.

## Alertes IFTTT

Le secret GitHub `IFTTT_WEBHOOK_URL` conserve la connexion existante à l’événement `race_radar_new`.
Une notification récapitule les nouvelles courses par rubrique, ainsi que les changements HYROX validés
(statut, ouverture, catégorie — dont Doubles Pro).
Le workflow se déclenche après chaque collecte réussie, y compris Cyclo, et dispose d’un rattrapage quotidien.

Les ouvertures HYROX sont appliquées depuis `hyrox_updates.json` après vérification d’une page officielle
d’événement HYROX. Les pistes RSS ne sont jamais des confirmations d’inscription.
Renseigner `category` avec la catégorie exacte annoncée ; une ouverture générale ne prouve pas
qu’il reste des places en Doubles Pro.

`.ifttt_seen.json` mémorise les courses et les annonces déjà signalées.
La première exécution initialise la mémoire sans alerte historique.
La migration de l’ancienne mémoire conserve les courses connues et initialise silencieusement les statuts HYROX.
Une rubrique envoyée avec succès est enregistrée avant de traiter la suivante.
En cas d’échec, les rubriques non envoyées sont réessayées à la prochaine exécution.
IFTTT ne fournit pas de garantie d’envoi exactement une fois en cas de coupure après réception du webhook.

## Vérifications sans notification réelle

```sh
python -m pip install 'beautifulsoup4>=4.12,<5'
python -m unittest discover -s tests -v
python -m unittest test_hyrox_apply test_hyrox_watch -v
node --test tests/test_dashboard.cjs
```

Les tests de notification utilisent une fonction d’envoi simulée et une mémoire temporaire.

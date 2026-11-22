# RACE//RADAR

Agenda Running, Trail, HYROX et Cyclo : https://thomasnast2-glitch.github.io/race-radar/

## Synchronisations

Les dates et formats vérifiés sur les pages des organisateurs figurent dans `official_events.json`. Ce registre est réappliqué avant les imports secondaires, qui ne doivent pas fusionner deux formats distincts ni remplacer les distances officielles. Les courses sur plusieurs jours conservent leur intervalle et leurs dates par format dans la fiche. Une date confirmée ne prouve pas la disponibilité des inscriptions.

L'état Running affiche les collectes indisponibles et les conflits de dates, même si la veille des liens ou le workflow réussit. Les exclusions de meetings de piste/salle sont conservées dans `excluded_events.json`.

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

## Fiches, distances et tarifs

Les cartes ouvrent une fiche sans quitter le calendrier. Le filtre Distance est
réservé à Running. Les tarifs officiels sont conservés dans `pricing.json` ;
à défaut, Running et Cyclo affichent une estimation clairement non officielle.
Voir [PRICING.md](PRICING.md) pour le format, les règles et les tests navigateur.

## Fiabilité et préparation de saison

Les cartes et les fiches distinguent « Vérifié sur le site officiel » et « À confirmer ».
Le badge vérifié exige `source_type: "official"`, une URL HTTP(S) et une date
`verified_at` valide, non future. La date reste visible : il s'agit d'une vérification
historique des informations, pas d'une promesse de places disponibles. Une course
marquée `certainty: "confirmée"` par un calendrier secondaire ne suffit pas.
Les contrôles de collecte, les tarifs et les annonces d'inscription HYROX gardent
leurs indicateurs séparés. Aucune nouvelle vérification officielle n'est inventée.

Les favoris existants restent dans `race-radar-favorites`, sans migration ni
réécriture au chargement. Le statut personnel « Intéressé », « Inscrit » ou
« Objectif principal » est enregistré séparément dans `race-radar-favorite-statuses`.
Sans statut enregistré, un ancien favori apparaît « Intéressé ». Retirer un favori
ne supprime pas son ancien statut : il est retrouvé si la course est ajoutée à nouveau.
Les statuts se synchronisent entre les onglets du même navigateur ; ils ne sont
pas partagés entre appareils et ne déclenchent aucune inscription ou notification.
Un stockage indisponible est signalé lors de la modification du statut.

Le bouton « Calendrier mensuel » réunit Running, HYROX et Cyclo. Les contrôles
permettent de changer de mois, revenir au mois courant, sélectionner une discipline
ou afficher uniquement les favoris. Les filtres des cartes restent indépendants ;
revenir à « Cartes » les conserve, changer de rubrique garde leur réinitialisation
habituelle. Le calendrier montre tout le mois, y compris les jours passés.
Une épreuve sur plusieurs jours figure chaque jour concerné, même à cheval sur
deux mois. Le compteur compte les événements uniques. Les dates non confirmées
restent dans une liste séparée, sans utiliser `sort` pour inventer un jour.
Sur téléphone, les jours avec événements sont présentés en liste lisible.
Chaque événement ouvre la fiche existante au clic ou au clavier.

Vérifier l'interface et le modèle sans contacter IFTTT :

```sh
npm install --ignore-scripts
npm test
npx playwright install chromium
npm run test:browser
```

Les tests couvrent les badges, la conservation des anciens favoris, les trois
statuts, la persistance, les onglets, les mois et années, les années bissextiles,
les événements sur plusieurs jours et les largeurs 1280, 390 et 320 pixels.

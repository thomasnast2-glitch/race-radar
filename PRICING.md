# Tarifs des fiches

`pricing.json` est indépendant des collectes : aucune modification de `events.json`
ou `cycling.json` n'est nécessaire. Les favoris conservent leur clé de stockage et
leurs identifiants. Aucun tarif officiel n'est prérempli sans vérification.

## Enregistrer un tarif vérifié

Le fichier contient `version: 1` et un objet `events` indexé par l'identifiant exact
de l'événement. Chaque entrée possède :

| Champ | Contenu |
|---|---|
| `eventDate` | Date ISO de l'édition, égale à `date` ou à `sort` si la date n'est pas confirmée |
| `distances` | Objet indexé par les kilomètres, en notation décimale avec point (`"21.1"`) |
| `categories` | Pour HYROX seulement : objet indexé par le nom exact de catégorie |

Chaque valeur de `distances` ou `categories` est un objet :

| Champ | Contenu |
|---|---|
| `status` | `"official"`, uniquement après vérification humaine sur la source officielle |
| `amount` | Montant exact en nombre, positif ou nul ; pas de chaîne de caractères |
| `currency` | `"EUR"` (autres devises non prises en charge actuellement) |
| `source` | URL HTTP(S) exacte de la page officielle attestant ce montant |
| `verifiedAt` | Date ISO de vérification, facultative mais recommandée |

Relever séparément chaque distance et chaque catégorie. Une page de calendrier
ou un tarif « à partir de » ne suffit pas à attester toutes les distances.
Le code contrôle le format des enregistrements, pas l'authenticité de la page :
la vérification humaine reste indispensable. Une date d'édition différente
invalide le tarif pour éviter de le reporter sur une autre année.
Un identifiant modifié par une collecte nécessite une nouvelle association manuelle.

## Estimations

`pricing.js`, objet `RULES`, définit pour chaque discipline quatre coefficients :
`[forfait_min, euros_par_km_min, forfait_max, euros_par_km_max]`.
Les bornes sont `forfait + distance × euros_par_km`, arrondies à l'euro.
Running distingue Route, Trail, Nature et Cross ; Cyclo distingue Route, Gravel
et Ultra. Ces règles génériques configurables ne sont pas calibrées sur les
organisateurs du calendrier et ne garantissent aucun prix.

Chaque distance valide reçoit soit un tarif officiel, soit une fourchette
« Tarif estimé — non officiel ». Discipline inconnue ou distance absente :
« Tarif à vérifier auprès de l'organisateur ». Aucun calcul de prix HYROX.
Les catégories HYROX ne sont affichées que si leur tarif vérifié est valide.
Les options, frais de plateforme, disponibilités et vagues tarifaires ne sont
pas connus ; le lien d'inscription permet de confirmer le montant actuel.

Un fichier de tarifs absent ou invalide ne bloque pas les courses : la fiche
signale son indisponibilité et conserve les estimations. Il n'y a pas d'API,
de clé ou de service payant.

## Tests

```sh
python -m pip install 'beautifulsoup4>=4.12,<5'
python -m unittest discover -s tests -v
python -m unittest test_collect_events test_hyrox_apply test_hyrox_watch -v
npm install --ignore-scripts
npm test
npx playwright install chromium
npm run test:browser
```

Les tests navigateur utilisent des événements et un tarif officiel fictifs
interceptés en mémoire, jamais ajoutés aux données publiées. Ils contrôlent
les largeurs 1280, 390 et 320 pixels, le clavier, les filtres combinés, les
liens, le calendrier et la persistance des favoris. Les tests de notifications
simulent les envois, sans contacter IFTTT. Un workflow de PR séparé exécute
ces contrôles sans collecte, notification ni publication Pages.

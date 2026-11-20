# Immo Loiret · où acheter autour d'Orléans, et à quel prix ?

Tableau de bord qui aide un couple d'acheteurs à décider **dans quelle commune ou quel quartier
chercher, pour quel budget**. Il s'appuie sur les 49 863 ventes de logements réellement conclues dans le
Loiret de janvier 2021 à juin 2026 (DVF, DGFiP).

| Période | Ventes | Source |
|---|---|---|
| 2021 – 2025 | 46 022 | DVF géolocalisées (Etalab) |
| 1er semestre 2026 | 3 841 | DVF brutes (DGFiP, publiées en octobre 2026), sans coordonnées |

## En ligne

| | Lien |
|---|---|
| **Dashboard** | https://immo-loiret-web.onrender.com |
| **API** | https://immo-loiret-api.onrender.com |
| **Documentation de l'API** (Swagger) | https://immo-loiret-api.onrender.com/docs |

> Hébergé sur l'offre gratuite de Render : après 15 minutes sans visite, les services se mettent en
> veille et la première ouverture peut prendre environ une minute.

Dès l'ouverture, la page d'accueil répond à trois questions :

| Question | Ce que montre l'appli |
|---|---|
| **Quel budget pour une maison de 100 m² ?** | Fourchette de prix, frais de notaire compris, de la commune la moins chère à la plus chère, et nombre de communes accessibles avec 300 000 € |
| **Où est-ce le moins cher, et le plus cher ?** | Carte du prix médian au m² par commune, maison ou appartement, et écart entre les deux |
| **Les prix ont-ils baissé depuis la hausse des taux ?** | Variation du €/m² médian et du nombre de ventes entre 2021-22 et 2024-25, commune par commune |

## Architecture

```
┌──────────────────────────┐   HTTP/JSON   ┌──────────────────────────┐
│ frontend/  (Dash)        │ ────────────▶ │ backend/  (FastAPI)      │
│ pages, cartes, graphes,  │               │ filtres, médianes,       │
│ thème, interactions      │ ◀──────────── │ fiabilité, GeoJSON       │
│ cache des réponses       │               │ données DVF (parquet)    │
└──────────────────────────┘               └──────────────────────────┘
```

- **backend/** : API REST FastAPI. C'est la seule partie qui lit les données. Elle calcule médianes, volumes, évolutions et budget, et porte les règles métier (seuil de fiabilité, frais de notaire, périodes comparées), exposées par `/meta`. Documentation interactive sur `/docs`.
- **frontend/** : application Dash (Mantine, AG Grid, Plotly). Elle n'a aucun accès direct aux données, tout passe par l'API (`frontend/immo/api.py`). Les réponses sont mises en cache côté serveur Dash.

Principaux endpoints (tous en `GET`, filtres en paramètres : `zone`, `annee_min/max`, `prix_min/max`, `surf_min/max`, `pm2_min/max`) :

| Endpoint | Rôle |
|---|---|
| `/meta`, `/communes`, `/geo/communes` | Constantes métier, liste des communes, contours GeoJSON |
| `/stats/kpis`, `/stats/communes`, `/stats/communes/comparees` | Chiffres clés et médianes par commune |
| `/stats/annuelles`, `/stats/trimestrielles`, `/stats/evolution[/communes]` | Tendances, avant et après 2022 |
| `/budget/communes` | Communes accessibles pour un budget et un bien |
| `/communes/{code}/resume`, `/quartiers`, `/quartiers/geo`, `/annuel`, `/ventes`, `/comparables` | Fiche commune et drill-down par quartier |
| `/adresses`, `/communes/{code}/autour` | Recherche d'adresse (Base Adresse Nationale) et prix autour d'un point |

## Les pages

- **Vue d'ensemble** : chiffres clés, réponses aux trois questions, carte cliquable et tendance sur 12 mois glissants.
- **Mon budget** : budget (frais de notaire inclus ou non), type, surface et nombre de pièces. Pour chaque commune, la part des ventes comparables qui tenaient dans le budget.
- **Communes** : carte, comparaison maison et appartement, tableau de toutes les communes.
- **Fiche commune** (drill-down **commune → quartier → vente**) : prix médian par quartier nommé (« Carmes-République », « Saint-Marceau »…), carte des quartiers colorés par prix, où un clic affiche les ventes du quartier, et tableau des ventes. Une vente sélectionnée est comparée aux ventes similaires (même type, surface à ±20 %).
- **Filtre par adresse** : sur la fiche commune (« Autour d'une adresse… ») ou depuis la page Communes (tout le Loiret), on tape une adresse et on choisit un rayon (300 m, 500 m, 1 km). La fiche montre alors les prix médians autour de cette adresse, comparés à la commune, ainsi que la carte et la liste des ventes dans le rayon, avec leur distance.
- **Tendances** : prix et volumes avant et après 2022, carte des variations, plus fortes baisses et hausses.
- **Méthodologie** : sources, filtres, choix de calcul et limites des données.

Sur toutes les pages, on peut basculer entre **Orléans Métropole** (vue par défaut) et **tout le Loiret**, ajuster les **filtres de données** et passer en **thème sombre**.

## Assistant (LLM Gemini)

L'appli intègre un assistant basé sur **Google Gemini** (offre gratuite), appelé uniquement par le backend, qui seul détient la clé.

| Fonction | Où | Ce que fait l'assistant |
|---|---|---|
| **Expliquer un prix** | page « Évaluer un prix » (annonce saisie) et vente sélectionnée d'une fiche commune | Explique l'écart avec les ventes comparables (même commune, même type, surface ±20 %) et propose une piste concrète |
| **Conseil budget** | page « Mon budget » | Indique où chercher en priorité et quels compromis envisager |
| **Discussion** | bulle en bas à droite de toutes les pages | Répond aux questions sur les prix, communes, quartiers, tendances et budget |

**Règle de fond : le LLM ne calcule rien.** L'API calcule les médianes, écarts et nombres de ventes ; Gemini ne fait que les expliquer. Pour la discussion, il dispose de quelques **outils** limités à nos données (`chercher_commune`, `prix_commune`, `prix_par_quartier`, `communes_pour_budget`, `classement_communes`, `evolution_des_prix`, `evolution_commune`, `evaluer_un_prix`) et doit citer le nombre de ventes qui fonde chaque chiffre.

**Garde-fous** : 20 demandes à l'assistant par visiteur et par session ; plafond global de requêtes par heure côté API (`LLM_QUOTA_HEURE`) pour préserver le quota gratuit ; délai maximal par appel ; **repli sans LLM** si Gemini ne répond pas (pas de clé, quota, panne) : les chiffres restent affichés, seul le texte manque. Sans clé configurée, la bulle et les boutons de l'assistant n'apparaissent pas.

> Sur l'offre gratuite de Gemini, Google peut utiliser les échanges pour améliorer ses produits : ne saisissez pas d'informations personnelles dans le chat.

## Serveur MCP

Le projet expose ses données par un serveur [MCP](https://modelcontextprotocol.io) (`backend/immo_api/mcp_server.py`, SDK officiel `mcp` 2.x). N'importe quel assistant compatible (Claude Code, Claude Desktop…) peut ainsi interroger les prix du Loiret, avec les mêmes calculs que le tableau de bord.

| Type | Contenu |
|---|---|
| **Outils** (lecture seule) | `chercher_commune`, `prix_commune`, `prix_par_quartier`, `communes_pour_budget`, `classement_communes`, `evolution_des_prix`, `evolution_commune`, `evaluer_un_prix`, `prix_autour_d_une_adresse` (géocodage IGN) |
| **Ressources** | `immo://regles` (seuil, frais, périodes, sources), `immo://communes`, `immo://communes/{code_commune}` (fiche avec quartiers) |
| **Prompt** | `evaluer_une_annonce` (commune, type, surface, prix) |

Le fichier `.mcp.json`, à la racine, déclare le serveur. **Claude Code** le propose automatiquement quand on ouvre le dépôt.

**Inspecter le serveur avec MCP Inspector** (Node.js requis), depuis la racine du dépôt :

```bash
npx @modelcontextprotocol/inspector --config .mcp.json --server immo-loiret
```

L'interface s'ouvre sur `http://127.0.0.1:6274`. Le jeton d'accès est affiché dans le terminal. Cliquez ensuite sur l'interrupteur du serveur `immo-loiret` pour vous connecter, puis explorez les outils, les ressources et le prompt.

En ligne de commande, sans interface :

```bash
npx @modelcontextprotocol/inspector --cli --config .mcp.json --server immo-loiret --method tools/list
npx @modelcontextprotocol/inspector --cli --config .mcp.json --server immo-loiret --method tools/call --tool-name evaluer_un_prix --tool-arg 'code_commune="45234"' --tool-arg type_bien=Appartement --tool-arg surface=60 --tool-arg prix=180000
```

Les codes INSEE se passent entre guillemets JSON (`'code_commune="45234"'`), sinon l'Inspector les convertit en nombres.

Le serveur peut aussi tourner en HTTP : `uv run python -m immo_api.mcp_server --http --port 8020` (point d'accès `/mcp`).

## Choix de méthode

- **Médianes, pas moyennes** : quelques ventes très chères ne déforment pas les prix.
- **Seuil de fiabilité à 30 ventes** : en dessous, une commune ou un quartier reste en gris et son prix est dit « indicatif ». Le nombre de ventes est toujours affiché.
- **Frais de notaire** : environ 7,5 % dans l'ancien, déductibles du budget avec une case à cocher.
- **Avant et après la hausse des taux** : deux périodes de deux ans (2021-22 et 2024-25) pour avoir assez de ventes par commune.
- **Limites** : DVF ne dit rien de l'état du bien, de l'étage ni du DPE. Les adresses sont retirées (le quartier est le niveau le plus fin) et le prix d'une maison inclut son terrain.

## Lancer en local

Chaque partie est un projet [uv](https://docs.astral.sh/uv/) indépendant. Deux terminaux :

```bash
# 1. API sur http://localhost:8000 (docs : http://localhost:8000/docs)
cd backend
uv sync
uv run uvicorn immo_api.main:app --reload --port 8000
```

```bash
# 2. Dashboard sur http://localhost:8050
cd frontend
uv sync
uv run python app.py
```

Pour activer l'assistant en local, copiez `backend/.env.example` en `backend/.env` (ignoré par Git) et renseignez `GEMINI_API_KEY` ([clé gratuite sur AI Studio](https://aistudio.google.com/apikey)).

Le frontend cherche l'API à l'adresse donnée par `API_URL` (par défaut `http://localhost:8000`). Si l'API tourne sur un autre port, par exemple `API_URL=http://localhost:8010`, il suffit de définir cette variable.

Tests de l'API :

```bash
cd backend
uv run pytest
```

Les contours des communes (`backend/data/communes_loiret.geojson`) sont dans le dépôt. Pour les régénérer : `uv run python scripts/prepare_geo.py` depuis `backend/`.

### Filtre par adresse

DVF ne publie pas les adresses des biens vendus : on ne peut donc pas filtrer « les ventes du 12 rue Bannier ». À la place, l'adresse saisie est localisée par la [Base Adresse Nationale](https://adresse.data.gouv.fr/) (géocodeur de la Géoplateforme IGN, `data.geopf.fr/geocodage`, appelé par le backend), puis on retient les ventes géolocalisées situées dans le rayon choisi.

- Les ventes de 2026, sans coordonnées, ne sont pas prises en compte autour d'une adresse.
- L'adresse cherchée ne passe jamais dans l'URL : elle reste en mémoire dans la page.

### Quartiers

Les sections cadastrales (« AB », « DX »…) ne parlaient pas aux acheteurs. La fiche commune raisonne donc par **quartiers IRIS** de l'INSEE : un découpage officiel d'environ 2 000 habitants, avec des noms connus des habitants. Orléans en compte 45 ; les petites communes forment un seul quartier, et la fiche passe alors directement aux ventes.

Chaque vente est placée dans son quartier par sa position (point dans le polygone). Les ventes sans coordonnées, dont toutes celles de 2026, le sont par leur section cadastrale, rattachée au quartier où tombent la plupart de ses ventes géolocalisées. Résultat : 49 859 ventes rattachées sur 49 863.

```bash
cd backend
uv run python scripts/prepare_quartiers.py chemin/vers/iris_loiret.geojson
```

La section cadastrale reste visible en dernière colonne du tableau des ventes, pour les utilisateurs avertis.

### Données 2026

Pour 2026, Etalab ne publie pas encore la version géolocalisée. Le fichier `backend/data/immobilier_2026s1.parquet` vient donc des [DVF brutes de la DGFiP](https://www.data.gouv.fr/datasets/demandes-de-valeurs-foncieres/) (`valeursfoncieres-2026-s1.txt.zip`, 32 Mo). Il est préparé avec les mêmes règles que le fichier d'origine : ventes d'un seul logement dans le Loiret, avec les mêmes bornes de prix, de surface et de prix au m².

```bash
cd backend
uv run python scripts/prepare_dvf_2026s1.py chemin/vers/valeursfoncieres-2026-s1.txt.zip
```

Contrôle : 3 841 ventes, contre 3 874 au premier semestre 2025, et des prix médians au m² proches (maisons 1 806 €, contre 1 813 €).

Ces ventes comptent dans toutes les statistiques. N'ayant pas de coordonnées, elles n'apparaissent pas sur la carte des ventes d'une commune. 2026 n'étant qu'un semestre, les graphiques annuels l'affichent « 2026 (janv.-juin) » en barre atténuée, et la comparaison avant/après la hausse des taux reste sur des années complètes (2021-22 contre 2024-25).

## Déploiement sur Render

`render.yaml` décrit deux services web (Render › New › Blueprint › ce dépôt) :

| Service | Dossier | Démarrage |
|---|---|---|
| `immo-loiret-api` | `backend/` | `uvicorn immo_api.main:app` |
| `immo-loiret-web` | `frontend/` | `gunicorn app:server` |

À la création, Render demande la variable `API_URL` du frontend : saisir l'URL publique de l'API, ici `https://immo-loiret-api.onrender.com`. Chaque service n'est reconstruit que si son propre dossier change.

Pour l'assistant, ajoutez la variable `GEMINI_API_KEY` au service `immo-loiret-api` (Render › service › Environment). La clé ne doit jamais être écrite dans le dépôt.

Sur l'offre gratuite, l'API se met en veille après 15 minutes sans trafic. La première visite peut donc afficher « Les données se réveillent… » le temps du redémarrage, environ une minute.

## Structure

```
backend/
  immo_api/
    main.py            # routes FastAPI, validation des paramètres
    data.py            # chargement, filtres et agrégats mémoïsés
    config.py          # règles métier (seuil, frais, périodes, bornes)
    geo.py             # distances, point dans un polygone, géocodage d'adresses
    llm.py             # client Gemini (assistant), garde-fous et repli
    outils.py          # outils de données partagés par l'assistant et le serveur MCP
    mcp_server.py      # serveur MCP du projet
  data/                # ventes DVF 2021-2025 et 2026 S1 (parquet), contours des communes
  scripts/
    prepare_geo.py         # contours des communes
    prepare_dvf_2026s1.py  # ventes du 1er semestre 2026 (DVF brutes)
    prepare_quartiers.py   # quartiers IRIS et rattachement des ventes
  tests/               # API, assistant (Gemini simulé), serveur MCP
frontend/
  app.py               # point d'entrée Dash (en-tête, filtres, thème) ; expose `server`
  theme.py             # couleurs, templates Plotly clair/sombre, thème Mantine
  immo/
    api.py             # client HTTP de l'API (avec cache)
    config.py          # constantes d'interface + règles métier lues sur /meta
    figures.py         # cartes et graphiques Plotly
    components.py      # tuiles KPI, cartes de réponse, AgGrid
    fmt.py             # formatage des nombres à la française
  pages/               # une page Dash par fichier
  assets/              # CSS et formateurs AG Grid
render.yaml            # déploiement des deux services
```

## Stack

**Backend** : FastAPI · pandas · pyarrow · uvicorn · google-genai (Gemini)
**Frontend** : Dash 3 · Dash Mantine Components · Dash AG Grid · Plotly · flask-caching · requests
**Outillage** : uv · pytest · black

## Sources et licences

- Ventes : **DGFiP, DVF**, Licence Ouverte 2.0. Pour 2021-2025, la version géolocalisée d'Etalab ; pour le 1er semestre 2026, la version brute de la DGFiP.
- Contours des communes : IGN Admin Express via [geo.api.gouv.fr](https://geo.api.gouv.fr), Licence Ouverte 2.0
- Quartiers : contours IRIS 2024 (IGN / INSEE) via [OpenDataSoft](https://public.opendatasoft.com/explore/dataset/georef-france-iris/), Licence Ouverte 2.0
- Adresses : Base Adresse Nationale, via le service de géocodage de la Géoplateforme (IGN), Licence Ouverte 2.0
- Fonds de carte : © OpenStreetMap contributors, © CARTO

Le cahier des charges d'origine est dans [`05-immobilier.md`](05-immobilier.md).

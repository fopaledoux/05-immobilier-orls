# Immo Loiret · où acheter autour d'Orléans, et à quel prix ?

Tableau de bord qui aide un couple d'acheteurs à décider **dans quelle commune ou quel quartier
chercher, pour quel budget**. Il s'appuie sur les 46 022 ventes de logements réellement conclues dans le
Loiret entre 2021 et 2025 (DVF, DGFiP).

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
| `/communes/{code}/resume`, `/sections`, `/annuel`, `/ventes`, `/comparables` | Fiche commune et drill-down |

## Les pages

- **Vue d'ensemble** : chiffres clés, réponses aux trois questions, carte cliquable et tendance sur 12 mois glissants.
- **Mon budget** : budget (frais de notaire inclus ou non), type, surface et nombre de pièces. Pour chaque commune, la part des ventes comparables qui tenaient dans le budget.
- **Communes** : carte, comparaison maison et appartement, tableau de toutes les communes.
- **Fiche commune** (drill-down **commune → section cadastrale → vente**) : prix par section, carte des ventes, tableau des ventes. Une vente sélectionnée est comparée aux ventes similaires (même type, surface à ±20 %).
- **Tendances** : prix et volumes avant et après 2022, carte des variations, plus fortes baisses et hausses.
- **Méthodologie** : sources, filtres, choix de calcul et limites des données.

Sur toutes les pages, on peut basculer entre **Orléans Métropole** (vue par défaut) et **tout le Loiret**, ajuster les **filtres de données** et passer en **thème sombre**.

## Choix de méthode

- **Médianes, pas moyennes** : quelques ventes très chères ne déforment pas les prix.
- **Seuil de fiabilité à 30 ventes** : en dessous, une commune ou une section reste en gris et son prix est dit « indicatif ». Le nombre de ventes est toujours affiché.
- **Frais de notaire** : environ 7,5 % dans l'ancien, déductibles du budget avec une case à cocher.
- **Avant et après la hausse des taux** : deux périodes de deux ans (2021-22 et 2024-25) pour avoir assez de ventes par commune.
- **Limites** : DVF ne dit rien de l'état du bien, de l'étage ni du DPE. Les adresses sont retirées (la section cadastrale est le niveau le plus fin) et le prix d'une maison inclut son terrain.

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

Le frontend cherche l'API à l'adresse donnée par `API_URL` (par défaut `http://localhost:8000`). Si l'API tourne sur un autre port, par exemple `API_URL=http://localhost:8010`, il suffit de définir cette variable.

Tests de l'API :

```bash
cd backend
uv run pytest
```

Les contours des communes (`backend/data/communes_loiret.geojson`) sont dans le dépôt. Pour les régénérer : `uv run python scripts/prepare_geo.py` depuis `backend/`.

## Déploiement sur Render

`render.yaml` décrit deux services web (Render › New › Blueprint › ce dépôt) :

| Service | Dossier | Démarrage |
|---|---|---|
| `immo-loiret-api` | `backend/` | `uvicorn immo_api.main:app` |
| `immo-loiret-web` | `frontend/` | `gunicorn app:server` |

À la création, Render demande la variable `API_URL` du frontend : saisir l'URL publique de l'API, ici `https://immo-loiret-api.onrender.com`. Chaque service n'est reconstruit que si son propre dossier change.

Sur l'offre gratuite, l'API se met en veille après 15 minutes sans trafic. La première visite peut donc afficher « Les données se réveillent… » le temps du redémarrage, environ une minute.

## Structure

```
backend/
  immo_api/
    main.py            # routes FastAPI, validation des paramètres
    data.py            # chargement, filtres et agrégats mémoïsés
    config.py          # règles métier (seuil, frais, périodes, bornes)
  data/                # ventes DVF (parquet) et contours des communes
  scripts/prepare_geo.py
  tests/test_api.py
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

**Backend** : FastAPI · pandas · pyarrow · uvicorn
**Frontend** : Dash 3 · Dash Mantine Components · Dash AG Grid · Plotly · flask-caching · requests
**Outillage** : uv · pytest · black

## Sources et licences

- Ventes : **DGFiP, DVF** (demandes de valeurs foncières géolocalisées, Etalab), Licence Ouverte 2.0
- Contours des communes : IGN Admin Express via [geo.api.gouv.fr](https://geo.api.gouv.fr), Licence Ouverte 2.0
- Fonds de carte : © OpenStreetMap contributors, © CARTO

Le cahier des charges d'origine est dans [`05-immobilier.md`](05-immobilier.md).

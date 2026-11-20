# Immo Loiret · où acheter autour d'Orléans, et à quel prix ?

Tableau de bord Dash qui aide un couple d'acheteurs à décider **dans quelle commune ou quel quartier
chercher, pour quel budget**. Il s'appuie sur les 46 022 ventes de logements réellement conclues dans le
Loiret entre 2021 et 2025 (DVF, DGFiP).

Dès l'ouverture, la page d'accueil répond à trois questions :

| Question | Ce que montre l'appli |
|---|---|
| **Quel budget pour une maison de 100 m² ?** | Fourchette de prix, frais de notaire compris, de la commune la moins chère à la plus chère, et nombre de communes accessibles avec 300 000 € |
| **Où est-ce le moins cher, et le plus cher ?** | Carte du prix médian au m² par commune, maison ou appartement, et écart entre les deux |
| **Les prix ont-ils baissé depuis la hausse des taux ?** | Variation du €/m² médian et du nombre de ventes entre 2021-22 et 2024-25, commune par commune |

## Les pages

- **Vue d'ensemble** : chiffres clés, réponses aux trois questions, carte cliquable et tendance sur 12 mois glissants.
- **Mon budget** : budget (frais de notaire inclus ou non), type, surface et nombre de pièces. Pour chaque commune, la part des ventes comparables qui tenaient dans le budget.
- **Communes** : carte, comparaison maison et appartement, tableau de toutes les communes.
- **Fiche commune** (drill-down **commune → section cadastrale → vente**) : prix par section, carte des ventes, tableau des ventes. Une vente sélectionnée est comparée aux ventes similaires (même type, surface à ±20 %).
- **Tendances** : prix et volumes avant et après 2022, carte des variations, plus fortes baisses et hausses.
- **Méthodologie** : sources, filtres, choix de calcul et limites des données.

Sur toutes les pages, on peut basculer entre **Orléans Métropole** (vue par défaut) et **tout le Loiret**, ajuster les **filtres de données** (années, prix, surface, €/m²) et passer en **thème sombre**.

## Choix de méthode

- **Médianes, pas moyennes** : quelques ventes très chères ne déforment pas les prix.
- **Seuil de fiabilité à 30 ventes** : en dessous, une commune ou une section reste en gris et son prix est dit « indicatif ». Le nombre de ventes est toujours affiché.
- **Frais de notaire** : environ 7,5 % dans l'ancien, déductibles du budget avec une case à cocher.
- **Avant et après la hausse des taux** : deux périodes de deux ans (2021-22 et 2024-25) pour avoir assez de ventes par commune.
- **Limites** : DVF ne dit rien de l'état du bien, de l'étage ni du DPE. Les adresses sont retirées (la section cadastrale est le niveau le plus fin) et le prix d'une maison inclut son terrain.

## Lancer en local

Le projet utilise [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run python app.py
```

Puis ouvrir http://localhost:8050.

Les contours des communes (`data/communes_loiret.geojson`) sont déjà dans le dépôt. Pour les régénérer :

```bash
uv run python scripts/prepare_geo.py
```

## Déploiement

- **Render** : le fichier `render.yaml` décrit le service (« New › Blueprint » en pointant sur ce dépôt). L'application tourne sous `gunicorn app:server`.
- **Railway** : le `Procfile` suffit. Railway installe les dépendances depuis `uv.lock` (ou `requirements.txt`).

`requirements.txt` est généré par `uv export --no-hashes --no-dev -o requirements.txt`.

## Structure

```
app.py                 # point d'entrée Dash (en-tête, filtres, thème) ; expose `server`
theme.py               # couleurs, templates Plotly clair/sombre, thème Mantine
immo/
  config.py            # constantes métier (seuil, frais, périodes, zones)
  data.py              # chargement, filtres et agrégats mémoïsés (flask-caching)
  figures.py           # cartes et graphiques Plotly
  components.py        # tuiles KPI, cartes de réponse, AgGrid
  fmt.py               # formatage des nombres à la française
pages/                 # une page Dash par fichier (dash.page_registry)
assets/                # CSS et formateurs AG Grid
data/                  # ventes DVF (parquet) et contours des communes
scripts/prepare_geo.py # téléchargement et simplification des contours
```

## Stack

Dash 3 · Dash Mantine Components · Dash AG Grid · Plotly · pandas · flask-caching · uv

## Sources et licences

- Ventes : **DGFiP, DVF** (demandes de valeurs foncières géolocalisées, Etalab), Licence Ouverte 2.0
- Contours des communes : IGN Admin Express via [geo.api.gouv.fr](https://geo.api.gouv.fr), Licence Ouverte 2.0
- Fonds de carte : © OpenStreetMap contributors, © CARTO

Le cahier des charges d'origine est dans [`05-immobilier.md`](05-immobilier.md).

# Étude sur la sirénisation de FINESS

Ce dépôt évalue et cherche à améliorer la qualité de l’appariement des entités
FINESS avec les identifiants du répertoire SIRENE.

L’étude porte sur deux niveaux dépendants :

- une **EJ** (entité juridique FINESS) se voit attribuer un SIREN ;
- un **EGE** (établissement géographique FINESS) se voit attribuer un SIRET.

Le terme *sirénisation* désigne ici ce processus de manière générale. On parle plus
spécifiquement de *sirétisation* pour l’appariement des EGE avec des SIRET.

Le projet combine préparation des données, construction des tables d’appariement,
échantillonnage stratifié, revue manuelle et analyse statistique pondérée. Les jobs
Python constituent l’implémentation opérationnelle. Le répertoire `project_tools/`
regroupe des outils complémentaires de développement, d’analyse ou d’évaluation,
hors du workflow numéroté.

## Documentation

- [Vue d’ensemble du projet et historique de l’étude](docs/PROJECT_OVERVIEW.md) :
  contexte, sources, méthodes d’appariement et historique de l’étude ;
- [Méthodologie statistique et glossaire](docs/METHODOLOGY.md) :
  populations, strates, plan de revue, pondération et indicateurs ;
- [Workflow et guide de maintenance](RUNBOOK.md) :
  profils de données, ordre d’exécution, prétraitement, tests et maintenance ;
- [Guide de l’évaluateur](docs/REVIEWER_GUIDE.md) :
  saisie et règles de revue manuelle.

Les PDF conservés dans `docs/` sont des références complémentaires.

## Démarrage rapide

Le projet utilise Python 3.12 et `uv`.

Depuis la racine du dépôt, synchronisez l’environnement :

```powershell
uv sync --locked
```

Pour travailler avec le profil de développement :

```powershell
$env:SIRENISATION_DATA_PROFILE = "dev"
```

Lancez les tests :

```powershell
uv run --locked pytest
```

Pour démarrer Jupyter afin d’utiliser un notebook :

```powershell
uv run --locked jupyter lab
```

Le profil `dev` utilise un sous-ensemble compact et cohérent des données pour le
développement et les tests. Le profil `full` utilise les données complètes et sert
à exécuter l’étude sur son périmètre complet.

Voir `RUNBOOK.md` pour la configuration des profils, l’organisation des données,
l’ordre d’exécution du workflow et les procédures de maintenance.

## Organisation du dépôt

- `00_prepare_data/` … `05_analyze_reviews/` : étapes opérationnelles du workflow ;
- `source_preprocessing/` : préparation reproductible des inputs FINESS, ANS et Adrien ;
- `data/` : données du profil `full` ;
- `results/` : outputs générés du profil `full` ;
- `dev/` : données et outputs du profil de développement ;
- `study_snapshots/` : copies figées des principaux livrables d’une version de l’étude ;
- `project_tools/` : outils complémentaires de développement, d’analyse et d’évaluation ;
- `tests/` : tests des comportements métier, relationnels, statistiques et des
  principales interfaces entre étapes ;
- `docs/` : documentation méthodologique, historique et guide de revue.

Le profil `dev` reproduit sous `dev/` la même séparation entre données et outputs que
le profil `full`. `study_snapshots/` conserve séparément les livrables figés d’une
version de l’étude, par exemple les résultats de l’étape 05, graphiques d’analyse,
analyses exploratoires retenues et échantillons annotés de référence partageables. Leur
organisation est documentée dans `RUNBOOK.md`.

## Conventions

Le code, les noms de modules, fonctions, variables, fichiers techniques et
répertoires sont rédigés en anglais. Les libellés et commentaires destinés
directement aux utilisateurs peuvent toutefois être rédigés en français. La
documentation destinée aux utilisateurs est rédigée en français. Les noms des fichiers
de documentation restent en anglais afin de conserver une convention homogène avec le
reste du dépôt.

## Auteur et contributions

Ce dépôt a été créé par Antoine Blot, élève attaché statisticien à l’ENSAI, dans le
cadre de son stage à la Drees de mai à août 2026, sous l’encadrement
d’Alexandre Cazenave-Lacroutz (OSAM/BES) et de Valérie Darriau (OSOL). Les travaux du
stage ont porté sur la conception méthodologique de l’étude, sa mise en œuvre statistique
et le développement du workflow et des traitements associés.

La méthodologie a également bénéficié des contributions d’Audrey Bergès, Benoît Fournier,
Guillaume Rateau et Jean-Claude Arbaut à la Drees, ainsi que de Laurent Dumontier,
Éric Sergent et Tahir Sabre Abdoulaye à l’ANS.

La constitution des échantillons annotés de référence a nécessité un travail collectif
de revue manuelle, auquel ont participé Audrey Bergès, Guillaume Rateau,
Benoît Fournier, Claire-Lise Dubost, Audrey Farges, Camille Schweitze,
Alexandre Cazenave-Lacroutz et Antoine Blot à la Drees, ainsi que Laurent Dumontier
et Tahir Sabre Abdoulaye à l’ANS.

L’étude évalue notamment deux méthodes d’appariement développées en amont : l’approche
ANS par Tahir Sabre Abdoulaye et Meryeme Chiboub à l’ANS, et l’approche Adrien par
Adrien Tortel, qui en a assuré la passation en début de stage. Jean-Claude Arbaut a
également assuré la passation de sa méthode d’appariement fondée sur les LLM, non
intégrée au workflow de l’étude mais mentionnée comme piste d’extension possible.

# Méthode de propositions Adrien

Adrien est une approche de génération de candidats multi-sources utilisée dans cette
étude comme source alternative de propositions d’appariement FINESS–SIRENE. Il ne
choisit pas directement un identifiant final unique : il produit des propositions
accompagnées d'informations sur la manière dont chaque proposition a été obtenue.

Ce document résume les inputs Adrien de juin 2026 utilisés par le projet. Le dépôt
prépare et évalue ces outputs ; il ne reproduit pas l'ensemble du système Adrien
amont.

## Propositions EGE / SIRET

Adrien fonctionne principalement au niveau des établissements FINESS.

Il évalue d'abord le SIRET déjà enregistré dans FINESS par rapport à SIRENE à l'aide
d'informations normalisées sur la dénomination et l'adresse. Les établissements non
retenus par cette concordance initiale peuvent recevoir des propositions alternatives
de SIRET provenant de plusieurs branches parallèles, notamment :

- d'autres établissements appartenant au même SIREN ;
- des liens de succession SIRENE directs ou indirects ;
- des sources externes de propositions ;
- un référentiel interne ;
- la variante de Claire Lelarge de la méthode d'extension par SIREN.

Certaines de ces sources, notamment la base de Claire Lelarge et le référentiel
interne, correspondent à des inputs figés qui ne sont plus maintenus. Leur contenu
peut donc progressivement s’écarter de l’état courant de FINESS et de SIRENE et
affecter les propositions produites sur des données plus récentes.

La génération de candidats et la validation lexicale sont des étapes distinctes :
certaines branches génèrent des candidats à partir d'identifiants ou de liens de
référentiel, après quoi la similarité de la dénomination et de l'adresse est évaluée.

Les outputs des différentes branches sont combinés tout en conservant la provenance
des sources. Un candidat peut donc être étayé par plusieurs sources. Les données
finales de propositions Adrien utilisées par ce projet contiennent des SIRET
candidats, plutôt qu'un appariement final sélectionné automatiquement.

Lors du prétraitement du projet, les lignes en double correspondant à une même paire
EGE FINESS/SIRET sont consolidées en prenant le score maximal de dénomination, en
réunissant les indicateurs de source et en recalculant le nombre de sources d'appui.

## Propositions EJ / SIREN

Adrien n'exécute pas d'algorithme d'appariement distinct au niveau des entités
juridiques pour les EJ.

Les propositions EJ sont construites à partir des propositions Adrien au niveau des
établissements. Chaque SIRET proposé est relié, via les données SIRENE de référence,
au SIREN correspondant. Les éléments de preuve obtenus sont ensuite regroupés par :

`FINESS EJ × proposed SIREN`.

Plusieurs propositions EGE/SIRET appartenant à une même EJ FINESS peuvent donc
étayer le même SIREN proposé.

Pour chaque paire EJ/SIREN, le projet conserve des informations de synthèse dérivées
des propositions sous-jacentes au niveau des établissements, notamment :

- le nombre de lignes SIRET servant d'appui ;
- les scores moyens de dénomination et d'adresse ;
- les indicateurs moyens de source ;
- le nombre de propositions provenant des étapes initiales et d'extension ;
- la part des éléments de preuve de l'EJ au niveau des établissements qui étaye ce
  SIREN.

La table Adrien obtenue au niveau EJ est donc une agrégation des éléments de preuve au
niveau des établissements, et non une source indépendante de propositions de SIREN.

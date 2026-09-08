# Extension du référentiel d'acronymes Adrien

## Objet

Ce travail vise à améliorer la couverture du référentiel d'acronymes utilisé par la
méthode Adrien à partir des dénominations FINESS.

La démarche a été :

1. extraire des tokens courts fréquents dans les dénominations FINESS ;
2. examiner les candidats et renseigner manuellement leur forme développée ;
3. écarter les tokens jugés non pertinents ;
4. ajouter les acronymes du référentiel Adrien qui n'étaient pas déjà couverts ;
5. fournir la liste consolidée à Adrien.

La sélection finale est donc un résultat de validation humaine et non la sortie
automatique d'un algorithme.

## Fichiers de référence

### `finess_acronym_final.xlsx`

Livrable final proposé à l'issue de ce travail. Le classeur contient 195 lignes dans
l'onglet `finess_acronym`, avec les colonnes `acronyme` et `nom_complet `.

Il correspond à nos résultats consolidés avec les quelques acronymes déjà présents
chez Adrien qui n'étaient pas couverts par notre sélection.

### `sigle_etab_finess.xlsx`

Référentiel actuellement utilisé en pratique par l'algorithme Adrien. Le premier
onglet, `liste_entiere`, est la liste opérationnelle consommée par l'algorithme ; les
autres onglets fournissent des vues par sous-ensemble ou secteur.

Le premier onglet contient actuellement les mêmes 195 lignes, dans le même ordre, que
`finess_acronym_final.xlsx`. Cette égalité a été vérifiée sur les colonnes
`acronyme` et `nom_complet `. Les 195 lignes correspondent à 194 acronymes distincts :
`USLD` est présent deux fois avec le même développé dans les deux fichiers. Le doublon
est laissé tel quel afin de conserver les artefacts de référence à l'identique.

Les deux classeurs sont conservés car ils documentent deux objets différents : le
résultat livré par ce travail et le référentiel effectivement utilisé par Adrien.

## Analyse de fréquence

`build_finess_acronym_frequency.py` reproduit uniquement l'étape exploratoire de
construction d'une table de fréquence de tokens courts. Par défaut, il lit
`PATHS.finess_ege_prepared` depuis `project_config`. Il utilise les colonnes
`nofinesset` et `rs`.

Depuis la racine du dépôt :

```powershell
uv run --locked python project_tools/extension_chaine_adrien/acronyms/build_finess_acronym_frequency.py
```

Le résultat est écrit dans :

`project_tools/extension_chaine_adrien/acronyms/output/finess_acronym_frequency.xlsx`

Le script déduplique les EGE par `nofinesset`, normalise les dénominations, retire un
petit ensemble de mots fonctionnels puis compte les tokens alphanumériques de huit
caractères ou moins. Les 1 000 tokens les plus fréquents sont exportés.

Cette table de fréquence est une aide à l'examen humain. Elle ne constitue ni le
référentiel final ni une procédure permettant de régénérer automatiquement le fichier
final proposé.

"""Orchestration des phases 2 et 3."""
import gc
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import BUDGET_MEMOIRE_GO
from src.matching import classifier_resultat
from src.scoring_vectorise import ConfigMatching, top_n_bloc, taille_lot


def lire_bloc(chemin_partitionne: Path, chemin_complet: Path,
              colonne_bloc: str, valeur: str) -> pd.DataFrame:
    """Lit un département depuis le parquet partitionné, ou à défaut depuis le
    parquet complet avec filtrage à la lecture."""
    # pyarrow relit "75" comme un entier et "2A" comme une chaîne
    formes = [valeur]
    if str(valeur).isdigit():
        formes.append(int(valeur))

    if Path(chemin_partitionne).exists():
        for forme in formes:
            try:
                df = pd.read_parquet(chemin_partitionne,
                                     filters=[(colonne_bloc, "==", forme)])
            except Exception:
                continue
            df[colonne_bloc] = str(valeur)
            return df

    for forme in formes:
        try:
            df = pd.read_parquet(chemin_complet,
                                 filters=[(colonne_bloc, "==", forme)])
        except Exception:
            continue
        df[colonne_bloc] = str(valeur)
        return df
    return pd.DataFrame()


def executer_phase(
    df_finess: pd.DataFrame,
    cfg: ConfigMatching,
    chemin_partitionne: Path,
    chemin_complet: Path,
    n: int,
    approfondi: bool = False,
    identifiants_deja_valides: Optional[set] = None,
    colonnes_sirene: Optional[list] = None,
    budget_go: float = BUDGET_MEMOIRE_GO,
    preparer_bloc=None,
    niveau_matching: str = "departement",
) -> pd.DataFrame:
    """
    Exécute une phase de matching probabiliste.

    `niveau_matching` fixe la maille de comparaison :

    - `"commune"` pour la phase 2 : une structure n'est comparée qu'aux
      candidats de sa propre commune ;
    - `"departement"` pour la phase 3, qui élargit la recherche.

    Dans les deux cas, la **lecture** du parquet se fait par département, seule
    maille de partitionnement. En blocking communal, chaque département est donc
    lu une fois puis découpé en communes en mémoire : on garde la sélectivité
    d'origine sans multiplier les accès disque par les 35 000 communes.

    preparer_bloc est appliquée à chaque bloc SIRENE après lecture ; la phase 3
    s'en sert pour dériver l'année de création.

    Les structures sans département exploitable, ou dont la maille ne contient
    aucun candidat, ressortent en SANS_CANDIDAT.
    """
    from tqdm.auto import tqdm

    identifiants_deja_valides = identifiants_deja_valides or set()
    colonnes_sirene = colonnes_sirene or []

    if niveau_matching not in ("commune", "departement"):
        raise ValueError("niveau_matching doit valoir 'commune' ou 'departement'")

    if niveau_matching == "commune":
        col_maille, col_maille_droite = cfg.col_commune, cfg.col_commune_droite
    else:
        col_maille, col_maille_droite = cfg.col_bloc, cfg.col_bloc_droite

    blocs = [b for b in df_finess[cfg.col_bloc].dropna().unique()
             if str(b) not in ("", "INCONNU")]
    blocs = sorted(blocs, key=str)

    sans_bloc = df_finess[~df_finess[cfg.col_bloc].isin(blocs)]
    resultats, orphelins = [], []

    if len(sans_bloc):
        print(f"{len(sans_bloc):,} structures sans departement exploitable")
        orphelins.append(_lignes_sans_candidat(sans_bloc, approfondi))

    libelle = "Phase 3 (departement)" if approfondi else f"Phase 2 ({niveau_matching})"
    for bloc in tqdm(blocs, desc=libelle):
        sous = df_finess[df_finess[cfg.col_bloc] == bloc]
        candidats = lire_bloc(chemin_partitionne, chemin_complet,
                              cfg.col_bloc_droite, str(bloc))
        if preparer_bloc is not None and len(candidats):
            candidats = preparer_bloc(candidats)

        if len(candidats) == 0:
            orphelins.append(_lignes_sans_candidat(sous, approfondi))
            del candidats
            continue

        if niveau_matching == "commune":
            groupes = candidats.groupby(col_maille_droite, sort=False)
            disponibles = set(groupes.groups)
            for maille, part_finess in sous.groupby(col_maille, sort=False):
                if not maille or maille not in disponibles:
                    orphelins.append(_lignes_sans_candidat(part_finess, approfondi))
                    continue
                resultats.append(top_n_bloc(
                    part_finess, groupes.get_group(maille), cfg, n=n,
                    approfondi=approfondi,
                    identifiants_deja_valides=identifiants_deja_valides,
                    colonnes_droite_a_garder=colonnes_sirene,
                    budget_go=budget_go))
            del groupes
        else:
            resultats.append(top_n_bloc(
                sous, candidats, cfg, n=n, approfondi=approfondi,
                identifiants_deja_valides=identifiants_deja_valides,
                colonnes_droite_a_garder=colonnes_sirene,
                budget_go=budget_go))

        del candidats
        gc.collect()

    df = pd.concat(resultats + orphelins, ignore_index=True) if (resultats or orphelins) \
        else pd.DataFrame()

    if len(df) and "statut_candidat" not in df.columns:
        df["statut_candidat"] = None
    if len(df):
        a_scorer = df["score_ajuste"].notna()
        df.loc[a_scorer, "statut_candidat"] = [
            classifier_resultat(r["score_ajuste"], r["score_nom"], r["score_adresse"])
            for _, r in df.loc[a_scorer].iterrows()
        ]
        df["statut_candidat"] = df["statut_candidat"].fillna("SANS_CANDIDAT")
    return df


def _lignes_sans_candidat(df: pd.DataFrame, approfondi: bool) -> pd.DataFrame:
    """Lignes conservées pour les structures qu'aucun bloc ne peut servir."""
    out = df.copy()
    out["nom_sirene_retenu"] = None
    for col in ("score_nom", "score_adresse", "score_global", "score_ajuste"):
        out[col] = None
    if approfondi:
        for col in ("score_ape", "score_date", "score_global_approfondi"):
            out[col] = None
    out["identifiant_coherent"] = False
    out["bonus_applique"] = False
    out["rang"] = 1
    out["statut_candidat"] = "SANS_CANDIDAT"
    return out


def estimer_charge(df_finess: pd.DataFrame, cfg: ConfigMatching,
                   tailles_blocs: pd.Series,
                   niveau_matching: str = "departement") -> pd.DataFrame:
    """Nombre de paires à scorer et taille de lot par maille.

    tailles_blocs doit être indexée par la même maille que niveau_matching.
    """
    col = cfg.col_commune if niveau_matching == "commune" else cfg.col_bloc
    compte = df_finess[col].value_counts().rename("nb_structures")
    est = pd.concat([compte, tailles_blocs.rename("nb_candidats")], axis=1).dropna()
    est["paires"] = est["nb_structures"] * est["nb_candidats"]
    est["lot_max"] = est["nb_candidats"].apply(lambda n: taille_lot(int(n)))
    est = est.sort_values("paires", ascending=False)
    print(f"Maille          : {niveau_matching}")
    print(f"Paires a scorer : {est['paires'].sum():,.0f}")
    print(f"Blocs           : {len(est)}")
    return est

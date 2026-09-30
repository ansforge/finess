"""Moteur de matching des phases 2 et 3."""
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process
from scipy import sparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    BUDGET_MEMOIRE_GO, N_MATRICES_PIC, BONUS_IDENTIFIANT_COHERENT,
)
from src.scoring import (
    W_LEV, W_JAC, W_TEXTUEL_NOM, W_INITIALES_NOM,
    W_COMMUNE, W_NUMERO_VOIE, W_LIBELLE_VOIE,
    W_NOM_GLOBAL, W_ADRESSE_GLOBAL,
    W_GLOBAL_APP_COMPLET, W_APE_COMPLET, W_DATE_COMPLET,
    W_GLOBAL_APP_PARTIEL, W_CRITERE_PARTIEL,
    normaliser_ape,
)


def _matrice_binaire(textes, vocabulaire):
    lignes, colonnes = [], []
    for k, t in enumerate(textes):
        for mot in set(t.split()):
            idx = vocabulaire.get(mot)
            if idx is not None:
                lignes.append(k)
                colonnes.append(idx)
    return sparse.csr_matrix(
        (np.ones(len(lignes), dtype=np.float64), (lignes, colonnes)),
        shape=(len(textes), max(len(vocabulaire), 1)))


def jaccard_matrice(a, b):
    """Jaccard sur les ensembles de mots, calculé par produit de matrices creuses."""
    voc = {}
    for t in list(a) + list(b):
        for mot in set(t.split()):
            voc.setdefault(mot, len(voc))
    ma, mb = _matrice_binaire(a, voc), _matrice_binaire(b, voc)

    inter = (ma @ mb.T).toarray()
    na = np.asarray(ma.sum(axis=1)).ravel()[:, None]
    nb = np.asarray(mb.sum(axis=1)).ravel()[None, :]
    union = na + nb - inter

    res = np.where(union > 0, inter / np.maximum(union, 1e-12) * 100.0, 0.0)
    vide_a, vide_b = (na == 0), (nb == 0)
    res = np.where(vide_a & vide_b, 100.0, res)
    return np.where(vide_a ^ vide_b, 0.0, res)


def lev_matrice(a, b, workers=-1):
    a, b = list(a), list(b)
    m = process.cdist(a, b, scorer=fuzz.ratio, workers=workers, dtype=np.float64)
    vide_a = np.array([not s for s in a])[:, None]
    vide_b = np.array([not s for s in b])[None, :]
    m = np.where(vide_a & vide_b, 100.0, m)
    return np.where(vide_a ^ vide_b, 0.0, m)


def textuel_matrice(a, b):
    return W_LEV * lev_matrice(a, b) + W_JAC * jaccard_matrice(a, b)


def initiales_matrice(a, b):
    ia = ["".join(w[0] for w in t.split() if w) for t in a]
    ib = ["".join(w[0] for w in t.split() if w) for t in b]
    m = lev_matrice(ia, ib)
    vide = (np.array([not s for s in a])[:, None]
            | np.array([not s for s in b])[None, :]
            | np.array([not s for s in ia])[:, None]
            | np.array([not s for s in ib])[None, :])
    return np.where(vide, 0.0, m)


def exact_matrice(a, b):
    sa = pd.Series(list(a), dtype=object).fillna("").astype(str)
    sb = pd.Series(list(b), dtype=object).fillna("").astype(str)
    codes, uniques = pd.factorize(pd.concat([sa, sb], ignore_index=True))
    ca, cb = codes[:len(sa)], codes[len(sa):]
    vides = np.where(np.asarray(uniques) == "")[0]
    code_vide = vides[0] if len(vides) else -999
    egal = (ca[:, None] == cb[None, :])
    renseigne = (ca[:, None] != code_vide) & (cb[None, :] != code_vide)
    return np.where(egal & renseigne, 100.0, 0.0)


def ape_matrice(ape_finess, ape_sirene):
    """NaN quand l'un des deux codes manque, le critère étant alors neutralisé."""
    a = np.array([normaliser_ape(x) for x in ape_finess], dtype=object)
    b = np.array([normaliser_ape(x) for x in ape_sirene], dtype=object)

    def prefixe(arr, n):
        return np.array([x[:n] if len(x) >= n else "" for x in arr], dtype=object)

    res = np.zeros((len(a), len(b)), dtype=np.float64)
    for n, valeur in ((2, 20.0), (3, 40.0), (4, 70.0)):
        pa, pb = prefixe(a, n), prefixe(b, n)
        res = np.where((pa[:, None] == pb[None, :]) & (pa[:, None] != ""), valeur, res)
    res = np.where((a[:, None] == b[None, :]) & (a[:, None] != ""), 100.0, res)

    manquant = (np.array([not x for x in a])[:, None]
                | np.array([not x for x in b])[None, :])
    return np.where(manquant, np.nan, res)


def date_matrice(annees_finess, annees_sirene):
    a = pd.to_numeric(pd.Series(list(annees_finess)), errors="coerce").to_numpy(dtype=float)
    b = pd.to_numeric(pd.Series(list(annees_sirene)), errors="coerce").to_numpy(dtype=float)
    ecart = np.abs(a[:, None] - b[None, :])

    res = np.zeros_like(ecart)
    for limite, valeur in ((20, 20.0), (10, 40.0), (5, 60.0), (3, 80.0), (1, 100.0)):
        res = np.where(ecart <= limite, valeur, res)
    return np.where(np.isnan(a)[:, None] | np.isnan(b)[None, :], np.nan, res)


@dataclass
class ConfigMatching:
    """Colonnes des deux côtés d'un appariement.

    cols_noms_droite est ordonnée par priorité : pour chaque paire on retient
    celle qui obtient le meilleur score textuel parmi les colonnes renseignées,
    les égalités allant à la première de la liste. col_nom_fallback_droite sert
    quand aucune n'est renseignée.
    """
    col_id: str
    col_nom: str
    col_commune: str
    col_num_voie: str
    col_voie: str
    col_bloc: str
    col_identifiant: str
    col_ape: Optional[str] = None
    col_annee: Optional[str] = None

    cols_noms_droite: list = field(default_factory=list)
    col_nom_fallback_droite: Optional[str] = None
    col_commune_droite: str = ""
    col_num_voie_droite: str = ""
    col_voie_droite: str = ""
    col_bloc_droite: str = ""
    col_identifiant_droite: str = ""
    col_ape_droite: Optional[str] = None
    col_annee_droite: Optional[str] = None


def taille_lot(n_candidats, budget_go=BUDGET_MEMOIRE_GO, n_matrices=N_MATRICES_PIC):
    """Nombre de lignes FINESS traitables en un lot sans dépasser le budget."""
    return max(1, int(budget_go * 1e9 / max(n_candidats * 8 * n_matrices, 1)))


def _choisir_nom(noms_gauche, df_droite, cfg):
    n_g, n_d = len(noms_gauche), len(df_droite)
    meilleur_textuel = np.full((n_g, n_d), -1.0)
    meilleur_initial = np.zeros((n_g, n_d))
    indice = np.full((n_g, n_d), -1, dtype=np.int16)
    trouve = np.zeros((n_g, n_d), dtype=bool)

    colonnes = [c for c in cfg.cols_noms_droite if c in df_droite.columns]
    valeurs = []

    for k, col in enumerate(colonnes):
        vals = df_droite[col].fillna("").astype(str).str.strip().tolist()
        valeurs.append(vals)
        renseigne = np.array([bool(v) for v in vals])[None, :]
        t = textuel_matrice(noms_gauche, vals)
        i = initiales_matrice(noms_gauche, vals)

        # strictement supérieur : à égalité la colonne prioritaire l'emporte
        remplace = renseigne & (~trouve | (t > meilleur_textuel))
        meilleur_textuel = np.where(remplace, t, meilleur_textuel)
        meilleur_initial = np.where(remplace, i, meilleur_initial)
        indice = np.where(remplace, k, indice)
        trouve = trouve | renseigne

    if cfg.col_nom_fallback_droite and cfg.col_nom_fallback_droite in df_droite.columns:
        repli = df_droite[cfg.col_nom_fallback_droite].fillna("").astype(str).str.strip().tolist()
    else:
        repli = [""] * n_d
    valeurs.append(repli)

    meilleur_textuel = np.where(trouve, meilleur_textuel, textuel_matrice(noms_gauche, repli))
    meilleur_initial = np.where(trouve, meilleur_initial, initiales_matrice(noms_gauche, repli))
    indice = np.where(trouve, indice, len(colonnes))

    table = np.array(valeurs, dtype=object)
    noms = np.take_along_axis(
        np.broadcast_to(table.T[None, :, :], (n_g, n_d, len(valeurs))),
        indice[:, :, None].astype(np.int64), axis=2)[:, :, 0]

    return meilleur_textuel, meilleur_initial, noms


def matrices_scores(df_gauche, df_droite, cfg, approfondi=False):
    noms_gauche = df_gauche[cfg.col_nom].fillna("").astype(str).tolist()
    textuel, initial, noms = _choisir_nom(noms_gauche, df_droite, cfg)

    score_nom = W_TEXTUEL_NOM * textuel + W_INITIALES_NOM * initial
    score_adresse = (
        W_COMMUNE * exact_matrice(df_gauche[cfg.col_commune], df_droite[cfg.col_commune_droite])
        + W_NUMERO_VOIE * exact_matrice(df_gauche[cfg.col_num_voie], df_droite[cfg.col_num_voie_droite])
        + W_LIBELLE_VOIE * textuel_matrice(
            df_gauche[cfg.col_voie].fillna("").astype(str).tolist(),
            df_droite[cfg.col_voie_droite].fillna("").astype(str).tolist())
    )
    score_global = W_NOM_GLOBAL * score_nom + W_ADRESSE_GLOBAL * score_adresse

    resultat = {"score_nom": score_nom, "score_adresse": score_adresse,
                "score_global": score_global, "nom_retenu": noms,
                "score_ape": None, "score_date": None,
                "score_global_approfondi": None}

    if approfondi:
        forme = score_global.shape
        a = (ape_matrice(df_gauche[cfg.col_ape], df_droite[cfg.col_ape_droite])
             if cfg.col_ape and cfg.col_ape_droite and cfg.col_ape in df_gauche.columns
             else np.full(forme, np.nan))
        d = (date_matrice(df_gauche[cfg.col_annee], df_droite[cfg.col_annee_droite])
             if cfg.col_annee and cfg.col_annee_droite and cfg.col_annee in df_gauche.columns
             else np.full(forme, np.nan))
        a_ok, d_ok = ~np.isnan(a), ~np.isnan(d)

        resultat["score_ape"] = a
        resultat["score_date"] = d
        resultat["score_global_approfondi"] = np.where(
            a_ok & d_ok,
            W_GLOBAL_APP_COMPLET * score_global
            + W_APE_COMPLET * np.nan_to_num(a) + W_DATE_COMPLET * np.nan_to_num(d),
            np.where(
                a_ok,
                W_GLOBAL_APP_PARTIEL * score_global + W_CRITERE_PARTIEL * np.nan_to_num(a),
                np.where(
                    d_ok,
                    W_GLOBAL_APP_PARTIEL * score_global + W_CRITERE_PARTIEL * np.nan_to_num(d),
                    score_global)))

    return resultat


def top_n_bloc(df_gauche, df_droite, cfg, n=5, approfondi=False,
               identifiants_deja_valides=None, colonnes_droite_a_garder=None,
               budget_go=BUDGET_MEMOIRE_GO):
    """Top n candidats pour chaque ligne FINESS d'un bloc, traité par lots.

    Le découpage en lots ne change pas le résultat, chaque ligne étant scorée
    indépendamment des autres. Les ex æquo sont départagés par l'identifiant
    SIRENE croissant, ce qui rend l'ordre reproductible.
    """
    if len(df_gauche) == 0 or len(df_droite) == 0:
        return pd.DataFrame()

    identifiants_deja_valides = identifiants_deja_valides or set()
    colonnes_droite_a_garder = colonnes_droite_a_garder or []
    cle_score = "score_global_approfondi" if approfondi else "score_global"

    ids_droite = df_droite[cfg.col_identifiant_droite].astype(str).to_numpy()
    ordre_egalite = np.argsort(np.argsort(ids_droite, kind="mergesort"))

    lot = taille_lot(len(df_droite), budget_go=budget_go)
    resultats = []

    for debut in range(0, len(df_gauche), lot):
        sous = df_gauche.iloc[debut:debut + lot]
        m = matrices_scores(sous, df_droite, cfg, approfondi=approfondi)
        base = np.round(m[cle_score], 2)

        ids_gauche = sous[cfg.col_identifiant].fillna("").astype(str).to_numpy()
        coherent = (ids_gauche[:, None] == ids_droite[None, :]) & (ids_gauche[:, None] != "")
        bonus_actif = np.array([bool(x) and x not in identifiants_deja_valides
                                for x in ids_gauche])[:, None]
        bonus = np.where(coherent & bonus_actif, BONUS_IDENTIFIANT_COHERENT, 0.0)
        ajuste = np.minimum(base + bonus, 100.0)

        k = min(n, ajuste.shape[1])
        rangs = np.lexsort(
            (np.broadcast_to(ordre_egalite, ajuste.shape), -ajuste), axis=1)[:, :k]

        sn = np.round(m["score_nom"], 2)
        sa = np.round(m["score_adresse"], 2)
        sg = np.round(m["score_global"], 2)
        sapp = np.round(m["score_global_approfondi"], 2) if approfondi else None

        for a in range(len(sous)):
            ligne_gauche = sous.iloc[a].to_dict()
            for rang, b in enumerate(rangs[a], start=1):
                ligne = {**ligne_gauche,
                         "nom_sirene_retenu": m["nom_retenu"][a, b],
                         "score_nom": float(sn[a, b]),
                         "score_adresse": float(sa[a, b]),
                         "score_global": float(sg[a, b]),
                         "identifiant_coherent": bool(coherent[a, b]),
                         "bonus_applique": bool(bonus[a, b] > 0),
                         "score_ajuste": float(ajuste[a, b]),
                         "rang": rang}
                if approfondi:
                    ape = m["score_ape"][a, b]
                    dte = m["score_date"][a, b]
                    ligne["score_ape"] = None if np.isnan(ape) else float(ape)
                    ligne["score_date"] = None if np.isnan(dte) else float(dte)
                    ligne["score_global_approfondi"] = float(sapp[a, b])
                for col in colonnes_droite_a_garder:
                    if col in df_droite.columns:
                        ligne[col] = df_droite.iloc[b][col]
                resultats.append(ligne)
        del m

    return pd.DataFrame(resultats)

"""Formules de scoring : textuel, nom, adresse, global, APE et date."""
from typing import Optional

import pandas as pd
from rapidfuzz import fuzz

# Poids du scoring textuel
W_LEV = 0.6
W_JAC = 0.4

# Poids du scoring nom
W_TEXTUEL_NOM   = 0.6
W_INITIALES_NOM = 0.4

# Poids du scoring adresse
W_COMMUNE      = 0.30
W_NUMERO_VOIE  = 0.30
W_LIBELLE_VOIE = 0.40

# Poids du scoring global
W_NOM_GLOBAL     = 0.4
W_ADRESSE_GLOBAL = 0.6

# Pondération de la phase 3
W_GLOBAL_APP_COMPLET = 0.70
W_APE_COMPLET        = 0.20
W_DATE_COMPLET       = 0.10
W_GLOBAL_APP_PARTIEL = 0.80
W_CRITERE_PARTIEL    = 0.20


def _levenshtein(s1: str, s2: str) -> float:
    if not s1 and not s2:
        return 100.0
    if not s1 or not s2:
        return 0.0
    return fuzz.ratio(s1, s2)


def _jaccard(s1: str, s2: str) -> float:
    if not s1 and not s2:
        return 100.0
    set1, set2 = set(s1.split()), set(s2.split())
    if not set1 or not set2:
        return 0.0
    return len(set1 & set2) / len(set1 | set2) * 100.0


def score_textuel(s1: str, s2: str) -> float:
    return W_LEV * _levenshtein(s1, s2) + W_JAC * _jaccard(s1, s2)


def score_initiales(s1: str, s2: str) -> float:
    """Compare les premières lettres de chaque mot."""
    if not s1 or not s2:
        return 0.0
    init1 = "".join(w[0] for w in s1.split() if w)
    init2 = "".join(w[0] for w in s2.split() if w)
    if not init1 or not init2:
        return 0.0
    return _levenshtein(init1, init2)


def calc_score_nom(nom_1: str, nom_2: str) -> float:
    return (W_TEXTUEL_NOM * score_textuel(nom_1, nom_2)
            + W_INITIALES_NOM * score_initiales(nom_1, nom_2))


def calc_score_adresse(
    code_commune_1: str, code_commune_2: str,
    numero_voie_1: str, numero_voie_2: str,
    libelle_voie_1: str, libelle_voie_2: str,
) -> float:
    def exact(a, b):
        if not a or not b:
            return 0.0
        return 100.0 if a == b else 0.0

    return (W_COMMUNE * exact(code_commune_1, code_commune_2)
            + W_NUMERO_VOIE * exact(numero_voie_1, numero_voie_2)
            + W_LIBELLE_VOIE * score_textuel(libelle_voie_1, libelle_voie_2))


def calc_score_global(score_nom: float, score_adresse: float) -> float:
    return W_NOM_GLOBAL * score_nom + W_ADRESSE_GLOBAL * score_adresse


# ─── APE et date (phase 3) ───────────────────────────────────────────────────

def extraire_annee(date_str) -> Optional[int]:
    """Année d'une date, quelle que soit sa forme. None si illisible."""
    if date_str is None or (isinstance(date_str, float) and pd.isna(date_str)):
        return None
    s = str(date_str).strip()
    if len(s) < 4:
        return None
    try:
        return int(s[:4])
    except ValueError:
        return None


def normaliser_ape(code) -> str:
    if code is None or (isinstance(code, float) and pd.isna(code)):
        return ""
    return str(code).strip().upper().replace(".", "").replace(" ", "")


def score_ape(ape_finess, ape_sirene) -> Optional[float]:
    """
    100 : codes identiques      70 : même classe (4 car.)
     40 : même groupe (3 car.)  20 : même division (2 car.)
      0 : aucune cohérence    None : un APE manquant, critère neutralisé
    """
    a, b = normaliser_ape(ape_finess), normaliser_ape(ape_sirene)
    if not a or not b:
        return None
    if a == b:
        return 100.0
    if a[:4] == b[:4]:
        return 70.0
    if a[:3] == b[:3]:
        return 40.0
    if a[:2] == b[:2]:
        return 20.0
    return 0.0


def score_date(annee_finess: Optional[int], annee_sirene: Optional[int]) -> Optional[float]:
    """100 si écart ≤ 1 an, puis 80 / 60 / 40 / 20 par paliers, 0 au-delà de 20 ans."""
    if annee_finess is None or annee_sirene is None:
        return None
    ecart = abs(annee_finess - annee_sirene)
    for limite, valeur in ((1, 100.0), (3, 80.0), (5, 60.0), (10, 40.0), (20, 20.0)):
        if ecart <= limite:
            return valeur
    return 0.0


def ponderation_approfondie(score_global_base: float,
                            s_ape: Optional[float],
                            s_date: Optional[float]) -> float:
    """Pondération adaptative de la phase 3, selon les critères disponibles."""
    if s_ape is not None and s_date is not None:
        return (W_GLOBAL_APP_COMPLET * score_global_base
                + W_APE_COMPLET * s_ape + W_DATE_COMPLET * s_date)
    if s_ape is not None:
        return W_GLOBAL_APP_PARTIEL * score_global_base + W_CRITERE_PARTIEL * s_ape
    if s_date is not None:
        return W_GLOBAL_APP_PARTIEL * score_global_base + W_CRITERE_PARTIEL * s_date
    return score_global_base

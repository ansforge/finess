"""Formules génériques de scoring (Levenshtein, Jaccard, initiales, adresse)."""
from rapidfuzz import fuzz
import pandas as pd

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


def _levenshtein(s1: str, s2: str) -> float:
    if not s1 and not s2:
        return 100.0
    if not s1 or not s2:
        return 0.0
    return fuzz.ratio(s1, s2)


def _jaccard(s1: str, s2: str) -> float:
    if not s1 and not s2:
        return 100.0
    set1 = set(s1.split())
    set2 = set(s2.split())
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
    return (
        W_TEXTUEL_NOM   * score_textuel(nom_1, nom_2)
        + W_INITIALES_NOM * score_initiales(nom_1, nom_2)
    )


def calc_score_adresse(
    code_commune_1: str, code_commune_2: str,
    numero_voie_1:  str, numero_voie_2:  str,
    libelle_voie_1: str, libelle_voie_2: str,
) -> float:
    def exact(a, b):
        if not a or not b:
            return 0.0
        return 100.0 if a == b else 0.0

    return (
        W_COMMUNE      * exact(code_commune_1, code_commune_2)
        + W_NUMERO_VOIE  * exact(numero_voie_1,  numero_voie_2)
        + W_LIBELLE_VOIE * score_textuel(libelle_voie_1, libelle_voie_2)
    )


def calc_score_global(score_nom: float, score_adresse: float) -> float:
    return W_NOM_GLOBAL * score_nom + W_ADRESSE_GLOBAL * score_adresse

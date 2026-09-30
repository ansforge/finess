"""Règles de validation et classification des résultats."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SEUIL_GLOBAL, SEUIL_NOM_MIN, SEUIL_ADRESSE_MIN


def est_valide(score_global: float, score_nom: float, score_adresse: float) -> bool:
    """
    Règle standard : score_global ≥ 67 OU (score_nom ≥ 15 ET score_adresse ≥ 55).
    """
    return (
        score_global >= SEUIL_GLOBAL
        or (score_nom >= SEUIL_NOM_MIN and score_adresse >= SEUIL_ADRESSE_MIN)
    )


def classifier_resultat(score_global: float, score_nom: float, score_adresse: float) -> str:
    """
    VALIDE_FORT : validé et score_global ≥ 85
    VALIDE      : validé
    DOUTEUX     : non validé, score_global ≥ 40
    REJETE      : non validé, score_global < 40
    """
    if est_valide(score_global, score_nom, score_adresse):
        return "VALIDE_FORT" if score_global >= 85 else "VALIDE"
    return "DOUTEUX" if score_global >= 40 else "REJETE"

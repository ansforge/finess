"""Modèle de fiabilité des propositions, par régression logistique pondérée.

Reprend la méthode d'Antoine Ablot (DREES) : logistique pondérée par les poids
calibrés du sondage, validation croisée à plis groupés par entité juridique,
évaluation par le score de Brier, l'AUC et la calibration.

Le modèle ne remplace pas les statuts : il ajoute une probabilité, qui permet de
choisir un seuil d'acceptation automatique plutôt que de reprendre en bloc.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def ajuster(X: pd.DataFrame, y: pd.Series, poids: pd.Series):
    """Logistique pondérée. X sans constante, elle est ajoutée ici."""
    return sm.GLM(y, sm.add_constant(X), family=sm.families.Binomial(),
                  freq_weights=poids).fit()


def odds_ratios(modele) -> pd.DataFrame:
    """Coefficients exponentiés, avec leur intervalle de confiance à 95 %."""
    bornes = modele.conf_int()
    return pd.DataFrame({
        "Variable": modele.params.index,
        "Coefficient": modele.params.values.round(3),
        "Odds ratio": np.exp(modele.params.values).round(2),
        "IC bas": np.exp(bornes[0].values).round(2),
        "IC haut": np.exp(bornes[1].values).round(2),
        "p-value": modele.pvalues.values.round(4),
    })


def predire_hors_echantillon(X: pd.DataFrame, y: pd.Series, poids: pd.Series,
                             groupes: pd.Series, n_plis: int = 5) -> pd.Series:
    """Probabilité de chaque observation, prédite par un modèle qui ne l'a pas vue.

    Les plis sont groupés par entité juridique : deux établissements d'une même
    PM partagent SIREN, adresse et souvent nom. Les séparer entre apprentissage
    et validation reviendrait à donner la réponse au modèle.
    """
    p = pd.Series(np.nan, index=X.index)
    for appr, test in GroupKFold(n_splits=n_plis).split(X, y, groupes):
        m = ajuster(X.iloc[appr], y.iloc[appr], poids.iloc[appr])
        p.iloc[test] = m.predict(sm.add_constant(X.iloc[test], has_constant="add"))
    return p


def metriques(y: pd.Series, p: pd.Series, poids: pd.Series) -> pd.DataFrame:
    """Brier, AUC et calibration globale, tous pondérés.

    Le Brier seul ne dit rien : on le compare à celui d'un modèle qui
    prédirait toujours le taux moyen. C'est l'écart entre les deux qui mesure
    l'apport des variables.
    """
    base = np.average(y, weights=poids)
    brier = np.average((y - p) ** 2, weights=poids)
    reference = np.average((y - base) ** 2, weights=poids)

    return pd.DataFrame([
        {"Metrique": "Score de Brier", "Valeur": round(brier, 4)},
        {"Metrique": "Brier de reference (taux moyen)", "Valeur": round(reference, 4)},
        {"Metrique": "Reduction du Brier", "Valeur": f"{(1 - brier / reference) * 100:.1f} %"},
        {"Metrique": "AUC", "Valeur": round(roc_auc_score(y, p, sample_weight=poids), 4)},
        {"Metrique": "Prediction moyenne", "Valeur": round(np.average(p, weights=poids), 4)},
        {"Metrique": "Taux observe", "Valeur": round(base, 4)},
        {"Metrique": "Observations", "Valeur": len(y)},
    ])


def calibration(y: pd.Series, p: pd.Series, poids: pd.Series,
                n_classes: int = 5) -> pd.DataFrame:
    """Compare, par classe de probabilité, ce que le modèle annonce et ce qu'on observe.

    C'est la vérification décisive : sans elle, un seuil de 0,90 ne veut rien
    dire. Parmi les cas annoncés à 0,90, on doit en trouver environ 90 % de
    corrects.
    """
    classes = pd.qcut(p, n_classes, labels=False, duplicates="drop")
    lignes = []
    for k in sorted(pd.Series(classes).dropna().unique()):
        m = classes == k
        lignes.append({
            "Classe": int(k) + 1,
            "Probabilite min": round(p[m].min(), 3),
            "Probabilite max": round(p[m].max(), 3),
            "Prediction moyenne": round(np.average(p[m], weights=poids[m]), 3),
            "Taux observe": round(np.average(y[m], weights=poids[m]), 3),
            "Effectif": int(m.sum()),
        })
    return pd.DataFrame(lignes)


def table_seuils(y: pd.Series, p: pd.Series, poids: pd.Series,
                 seuils=None) -> pd.DataFrame:
    """Volume accepté et taux correct, pour une gamme de seuils.

    Monter le seuil augmente la précision et réduit le volume. Le tableau rend
    cet arbitrage explicite : c'est lui qui fonde le choix, pas une valeur
    décidée d'avance.
    """
    if seuils is None:
        seuils = [0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.92, 0.95, 0.97]

    total = poids.sum()
    lignes = []
    for s in seuils:
        acceptes = p >= s
        part = poids[acceptes].sum() / total * 100
        correct = (np.average(y[acceptes], weights=poids[acceptes]) * 100
                   if acceptes.any() else np.nan)
        rejetes_corrects = (np.average(y[~acceptes], weights=poids[~acceptes]) * 100
                            if (~acceptes).any() else np.nan)
        lignes.append({
            "Seuil": s,
            "Acceptes (%)": round(part, 1),
            "Corrects parmi acceptes (%)": round(correct, 1),
            "Erreur residuelle (%)": round(100 - correct, 1),
            "Corrects parmi rejetes (%)": round(rejetes_corrects, 1),
            "Structures acceptees": int(acceptes.sum()),
        })
    return pd.DataFrame(lignes)


def appliquer(modele, X: pd.DataFrame) -> pd.Series:
    """Probabilité pour des structures hors échantillon d'estimation."""
    return modele.predict(sm.add_constant(X, has_constant="add"))

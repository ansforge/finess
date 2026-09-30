"""Phase 1 bis (sirenisation) — rejeu du score adresse avec les adresses
alternatives/historiques du SIREN.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ─── Score adresse spécifique Phase 1 bis (scénario 2) ───────────────────────

def calc_score_adresse_bis(
    code_commune_1: str, code_commune_2: str,
    numero_voie_1:  str, numero_voie_2:  str,
    libelle_voie_1: str, libelle_voie_2: str,
) -> float:
    """
    Score adresse SPÉCIFIQUE à la Phase 1 bis (scénario 2) — n'affecte PAS le
    pipeline principal qui continue d'utiliser src.scoring.calc_score_adresse.

    Règle de présence des composantes :
      - Absente des DEUX côtés → ignorée (rien à comparer).
      - Présente d'UN SEUL côté → conservée et comparée normalement
        (elle ne peut pas matcher → elle pénalise, ce qui reflète l'incertitude).
      - Présente des DEUX côtés → comparée normalement.

    Calcul :
      - Si toutes les composantes retenues sont présentes des DEUX côtés ET
        strictement identiques → 100 (égalité stricte).
      - Sinon → pondération dynamique (poids commune 0.30 / numéro 0.30 /
        libellé 0.40) redistribués sur les seules composantes retenues.
      - Aucune composante retenue (tout vide des deux côtés) → 0.
    """
    from src.scoring import (
        score_textuel, W_COMMUNE, W_NUMERO_VOIE, W_LIBELLE_VOIE,
    )

    composantes = []        # (poids, score) sur les composantes retenues
    egalite_stricte = True  # vrai si toutes retenues présentes des 2 côtés ET égales

    def _retenir(v1, v2, poids, est_exact):
        """Retourne (garder, score, contribue_egalite_stricte)."""
        p1, p2 = bool(v1), bool(v2)
        if not p1 and not p2:
            return False, 0.0, True            # absente des deux → ignorée
        if p1 != p2:
            # présente d'un seul côté → comparée, score 0, casse l'égalité stricte
            return True, 0.0, False
        # présente des deux côtés
        if est_exact:
            egal = v1 == v2
            return True, (100.0 if egal else 0.0), egal
        else:
            s = score_textuel(v1, v2)
            return True, s, (v1 == v2)

    for v1, v2, poids, exact in [
        (code_commune_1, code_commune_2, W_COMMUNE,      True),
        (numero_voie_1,  numero_voie_2,  W_NUMERO_VOIE,  True),
        (libelle_voie_1, libelle_voie_2, W_LIBELLE_VOIE, False),
    ]:
        garder, score, contribue = _retenir(v1, v2, poids, exact)
        if garder:
            composantes.append((poids, score))
            egalite_stricte = egalite_stricte and contribue

    if not composantes:
        return 0.0
    if egalite_stricte:
        return 100.0

    poids_total = sum(p for p, _ in composantes)
    return sum(p * s for p, s in composantes) / poids_total


# ─── Construction des adresses alternatives par SIREN ────────────────────────

def construire_adresses_alternatives(df_etab_all: pd.DataFrame) -> pd.DataFrame:
    """
    À partir de TOUS les établissements SIRENE (actifs ET fermés), produit une
    table des adresses candidates par SIREN, normalisées exactement comme les UL.

    Entrée attendue (colonnes brutes SIRENE) :
        siren, numeroVoieEtablissement, typeVoieEtablissement,
        libelleVoieEtablissement, codeCommuneEtablissement,
        etatAdministratifEtablissement, etablissementSiege

    Sortie (une ligne par établissement) :
        siren, numero_voie_norm_ul, libelle_voie_complet_ul,
        code_commune_norm_ul, etat, est_siege
    """
    from src.pretraitement import (
        pretraiter_numero_voie, mapper_type_voie,
        pretraiter_libelle_voie, pretraiter_code_commune,
    )

    df = df_etab_all.copy()
    df["siren"] = df["siren"].astype(str).str.strip()

    df["numero_voie_norm_ul"]  = df["numeroVoieEtablissement"].apply(pretraiter_numero_voie)
    type_voie                  = df["typeVoieEtablissement"].apply(mapper_type_voie)
    libelle_voie               = df["libelleVoieEtablissement"].apply(pretraiter_libelle_voie)
    df["libelle_voie_complet_ul"] = (type_voie + " " + libelle_voie).str.strip()
    df["code_commune_norm_ul"] = df["codeCommuneEtablissement"].apply(pretraiter_code_commune)

    df["etat"]      = df.get("etatAdministratifEtablissement", "")
    df["est_siege"] = df.get("etablissementSiege", "")

    cols = ["siren", "numero_voie_norm_ul", "libelle_voie_complet_ul",
            "code_commune_norm_ul", "etat", "est_siege"]
    df = df[cols].drop_duplicates().reset_index(drop=True)
    return df


# ─── Rejeu du score adresse pour une PM ──────────────────────────────────────

def rejouer_adresse_pm(row_pm: pd.Series, adresses_siren: pd.DataFrame) -> dict:
    """
    Recalcule le meilleur score adresse d'une PM contre toutes les adresses
    alternatives de son SIREN. Conserve le score_nom de la Phase 1.

    Retourne un dict avec le meilleur score adresse, le nouveau score global,
    le nouveau statut, et la trace de l'adresse gagnante.
    """
    from src.scoring import calc_score_global
    from src.matching import classifier_resultat

    score_nom = float(row_pm.get("score_nom") or 0.0)

    cc_pm = str(row_pm.get("cdcommune_norm_pm", ""))
    nv_pm = str(row_pm.get("nmvoie_norm_pm", ""))
    lv_pm = str(row_pm.get("libelle_voie_complet_pm", ""))

    # Point de départ : on démarre à 0 et on laisse le rejeu (score v2 scénario 2)
    meilleur_sa   = 0.0
    meilleure_adr = None
    meilleur_etat = None

    for _, adr in adresses_siren.iterrows():
        sa = calc_score_adresse_bis(
            cc_pm, str(adr.get("code_commune_norm_ul", "")),
            nv_pm, str(adr.get("numero_voie_norm_ul", "")),
            lv_pm, str(adr.get("libelle_voie_complet_ul", "")),
        )
        if sa > meilleur_sa:
            meilleur_sa   = sa
            meilleure_adr = (f"{adr.get('numero_voie_norm_ul','')} "
                             f"{adr.get('libelle_voie_complet_ul','')} "
                             f"({adr.get('code_commune_norm_ul','')})").strip()
            meilleur_etat = adr.get("etat", "")

    nouveau_global = calc_score_global(score_nom, meilleur_sa)
    nouveau_statut = classifier_resultat(nouveau_global, score_nom, meilleur_sa)

    return {
        "score_adresse_bis":   round(meilleur_sa, 2),
        "score_global_bis":    round(nouveau_global, 2),
        "statut_bis":          nouveau_statut,
        "adresse_alt_retenue": meilleure_adr,
        "etat_etab_retenu":    meilleur_etat,
    }


# ─── Application Phase 1 bis sur les PM non VALIDE_FORT ──────────────────────

def appliquer_phase1_bis(
    df_p1: pd.DataFrame,
    df_adresses_alt: pd.DataFrame,
    statuts_a_rejouer=("VALIDE", "DOUTEUX", "REJETE"),
    show_progress: bool = True,
) -> pd.DataFrame:
    """
    Rejoue le score adresse pour les PM dont la Phase 1 n'a pas donné
    VALIDE_FORT.

    df_p1           : résultats de la Phase 1 (sortie de matching_direct_siren)
    df_adresses_alt : sortie de construire_adresses_alternatives (indexée SIREN)
    statuts_a_rejouer : statuts P1 concernés par le rejeu (défaut : tout sauf
                        VALIDE_FORT — option principale d'Alexandre).

    Ajoute les colonnes *_bis et met à jour statut/score si le rejeu améliore.
    Trace l'origine via `phase1bis_applique` et `phase1bis_gain`.
    """
    from tqdm.auto import tqdm

    df = df_p1.copy()
    adr_idx = df_adresses_alt.set_index("siren")

    # colonnes de sortie initialisées
    df["score_adresse_bis"]   = df["score_adresse"]
    df["score_global_bis"]    = df["score_global"]
    df["statut_bis"]          = df["statut"]
    df["adresse_alt_retenue"] = None
    df["etat_etab_retenu"]    = None
    df["phase1bis_applique"]  = False
    df["phase1bis_gain"]      = None

    # on ne rejoue que les PM avec un SIREN lié et un statut concerné
    masque = df["statut"].isin(statuts_a_rejouer) & df["siren_ul"].notna()
    idx_rejeu = df[masque].index

    rows = idx_rejeu
    if show_progress:
        rows = tqdm(idx_rejeu, desc="Phase 1 bis (rejeu adresse)")

    # Rang des statuts pour ne retenir le rejeu que s'il AMÉLIORE (jamais dégrader)
    rang_statut = {"REJETE": 0, "DOUTEUX": 1, "VALIDE": 2, "VALIDE_FORT": 3}

    for i in rows:
        row_pm = df.loc[i]
        siren = str(row_pm.get("siren_ul", "") or "").strip()
        if not siren or siren not in adr_idx.index:
            continue

        adresses_siren = adr_idx.loc[[siren]]
        res = rejouer_adresse_pm(row_pm, adresses_siren)

        df.at[i, "phase1bis_applique"] = True

        # On ne remplace le résultat que si le rejeu améliore le statut.
        # Sinon on conserve le résultat de la Phase 1 (pas de dégradation).
        rang_avant = rang_statut.get(row_pm["statut"], -1)
        rang_apres = rang_statut.get(res["statut_bis"], -1)

        if rang_apres > rang_avant:
            df.at[i, "score_adresse_bis"]   = res["score_adresse_bis"]
            df.at[i, "score_global_bis"]    = res["score_global_bis"]
            df.at[i, "statut_bis"]          = res["statut_bis"]
            df.at[i, "adresse_alt_retenue"] = res["adresse_alt_retenue"]
            df.at[i, "etat_etab_retenu"]    = res["etat_etab_retenu"]
            df.at[i, "phase1bis_gain"]      = f"{row_pm['statut']} → {res['statut_bis']}"

    return df

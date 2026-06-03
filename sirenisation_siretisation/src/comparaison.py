"""
Comparaison de cohérence SIREN ↔ SIRET — Vue A (par EJ et ses EG).

Logique :
    - Une ligne = un couple (EJ, EG) où l'EG est rattaché à l'EJ via
      nmfinessej_stru côté EG.
    - Pour chaque couple, on compare SIRET_EG[:9] avec SIREN_EJ retenu
      en sirenisation.

Statuts de cohérence par couple :
    COHERENT   : EG validé + EJ validé + SIRET_EG[:9] == SIREN_EJ
    INCOHERENT : EG validé + EJ validé + SIRET_EG[:9] ≠ SIREN_EJ
    PARTIEL_EG : EG validé mais EJ parent non validé en sirenisation
    PARTIEL_EJ : EJ validé mais aucun EG validé en siretisation
    ORPHELIN   : EG validé sans nmfinessej_stru renseigné

Source : fichiers de phase (P1, P2, P3) fusionnés à la volée.
Sortie : un seul DataFrame "vue A" prêt à être exporté en Excel à 4 feuilles
(Synthese, Coherent, Incoherent, Partiel).
"""
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


VALIDES = {"VALIDE_FORT", "VALIDE"}


# ─── Utilitaires ─────────────────────────────────────────────────────────────

def _norm_id(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    return re.sub(r"\s", "", str(val).strip())


def _siren_from_siret(siret) -> str:
    s = _norm_id(siret)
    return s[:9] if len(s) >= 9 else ""


def _pick_first_non_null(row, cols):
    """Retourne la première valeur non nulle/non vide parmi les colonnes."""
    for col in cols:
        val = row.get(col)
        if val is not None and not (isinstance(val, float) and pd.isna(val)):
            s = str(val).strip()
            if s:
                return s
    return ""


# ─── Mappings statut ─────────────────────────────────────────────────────────

MAP_ST = {
    "Valide_fort": "VALIDE_FORT", "Valide": "VALIDE",
    "Douteux": "DOUTEUX", "Rejeté": "REJETE",
    "Sans_SIRET": "SANS_SIRET", "SIRET_inconnu": "SIRET_INCONNU",
    "Sans_candidat": "SANS_CANDIDAT",
}

MAP_SN = {
    "Valide_fort": "VALIDE_FORT", "Valide": "VALIDE",
    "Douteux": "DOUTEUX", "Rejeté": "REJETE",
    "Sans_SIREN": "SANS_SIREN", "SIREN_inconnu": "SIREN_INCONNU",
    "Sans_candidat": "SANS_CANDIDAT",
}


# ─── Chargement et fusion des 3 fichiers de phase ────────────────────────────

def charger_et_fusionner_phases(
    chemin_p1, chemin_p2, chemin_p3,
    type_pipeline: str,
) -> pd.DataFrame:
    """
    Fusionne les 3 fichiers de phase (siretisation OU sirenisation) en un seul
    DataFrame équivalent à l'ancienne consolidation finale.

    Logique :
        1. Phase 1 : tous les EG/EJ tels quels avec phase=1
        2. Phase 2 (rang 1) : ceux non validés en P1, avec phase=2
        3. Phase 3 (rang 1) : ceux non validés en P1 ni P2, avec phase=3

    Args:
        chemin_p1 : fichier phase 1 (ex: ST_PHASE1)
        chemin_p2 : fichier phase 2 top5 (ex: ST_PHASE2)
        chemin_p3 : fichier phase 3 top3 (ex: ST_PHASE3)
        type_pipeline : 'siretisation' ou 'sirenisation'
    """
    mapping = MAP_ST if type_pipeline == 'siretisation' else MAP_SN

    # ─── Phase 1 ────────────────────────────────────────────────────────────
    sheets_p1 = pd.read_excel(chemin_p1, sheet_name=None, dtype=str)
    dfs_p1 = []
    for nom, sdf in sheets_p1.items():
        if nom == "Synthèse":
            continue
        sdf = sdf.copy()
        sdf["statut"] = mapping.get(nom, nom)
        sdf["phase"] = 1
        dfs_p1.append(sdf)
    df_p1 = pd.concat(dfs_p1, ignore_index=True) if dfs_p1 else pd.DataFrame()

    # ─── Phase 2 (rang 1 uniquement) ────────────────────────────────────────
    df_p2 = pd.read_excel(chemin_p2, sheet_name='Top5', dtype=str)
    df_p2["rang"] = pd.to_numeric(df_p2["rang"], errors="coerce")
    df_p2 = df_p2[df_p2["rang"] == 1].copy()
    df_p2["phase"] = 2
    if "statut_candidat" in df_p2.columns:
        df_p2 = df_p2.rename(columns={"statut_candidat": "statut"})

    # ─── Phase 3 (rang 1 uniquement) ────────────────────────────────────────
    df_p3 = pd.read_excel(chemin_p3, sheet_name='Top3', dtype=str)
    df_p3["rang"] = pd.to_numeric(df_p3["rang"], errors="coerce")
    df_p3 = df_p3[df_p3["rang"] == 1].copy()
    df_p3["phase"] = 3
    if "statut_candidat" in df_p3.columns:
        df_p3 = df_p3.rename(columns={"statut_candidat": "statut"})

    # ─── Fusion en cascade ──────────────────────────────────────────────────
    # On garde tout le P1
    # On garde du P2 ce qui n'est pas déjà validé en P1
    # On garde du P3 ce qui n'est pas déjà validé en P1 ni P2
    ids_v1 = set(
        df_p1[df_p1["statut"].isin(VALIDES)]["idstructure_stru"]
        .dropna().astype(str)
    )
    df_p2_filtre = df_p2[~df_p2["idstructure_stru"].astype(str).isin(ids_v1)].copy()

    ids_v2 = set(
        df_p2_filtre[df_p2_filtre["statut"].isin(VALIDES)]["idstructure_stru"]
        .dropna().astype(str)
    )
    df_p3_filtre = df_p3[
        ~df_p3["idstructure_stru"].astype(str).isin(ids_v1 | ids_v2)
    ].copy()

    df_fusion = pd.concat([df_p1, df_p2_filtre, df_p3_filtre], ignore_index=True)
    return df_fusion


def charger_siretisation_depuis_phases(chemin_p1, chemin_p2, chemin_p3) -> pd.DataFrame:
    """Reconstruit la consolidation siretisation à partir des 3 fichiers de phase."""
    return charger_et_fusionner_phases(chemin_p1, chemin_p2, chemin_p3, 'siretisation')


def charger_sirenisation_depuis_phases(chemin_p1, chemin_p2, chemin_p3) -> pd.DataFrame:
    """Reconstruit la consolidation sirenisation à partir des 3 fichiers de phase."""
    return charger_et_fusionner_phases(chemin_p1, chemin_p2, chemin_p3, 'sirenisation')


# ─── Construction de la vue A ────────────────────────────────────────────────

def construire_vue_a(
    df_st: pd.DataFrame,
    df_sn: pd.DataFrame,
) -> pd.DataFrame:
    """
    Construit la vue A : une ligne par couple (EJ, EG) avec verdict de cohérence.

    Clé de jointure : nmfinessej_stru (numéro FINESS à 9 chiffres de l'EJ)
    - côté EG (df_st) : pointe vers l'EJ parent
    - côté EJ (df_sn) : c'est son propre numéro FINESS

    NB : idstructure_stru est un ID interne SQL différent des deux côtés
    (ID de l'EG côté ST, ID de l'EJ côté SN). On ne s'en sert PAS pour joindre.
    """
    df_st = df_st.copy()
    df_sn = df_sn.copy()

    # ─── Préparation siretisation (EG) ──────────────────────────────────────
    df_st["nmfinessej_stru_norm"] = df_st.get(
        "nmfinessej_stru", pd.Series(dtype=str)
    ).apply(_norm_id)

    cols_siret = ["siret_etab", "siret_ref", "siret_ref_app"]
    df_st["siret_retenu"] = df_st.apply(
        lambda r: _pick_first_non_null(r, cols_siret), axis=1
    )
    df_st["siret_retenu"] = df_st["siret_retenu"].apply(_norm_id)
    df_st["siren_from_siret"] = df_st["siret_retenu"].apply(_siren_from_siret)
    df_st["phase"] = pd.to_numeric(df_st.get("phase"), errors="coerce")

    # ─── Préparation sirenisation (EJ) ──────────────────────────────────────
    # Clé = nmfinessej_stru côté EJ (c'est son propre numéro FINESS public)
    df_sn["nmfinessej_stru_norm"] = df_sn.get(
        "nmfinessej_stru", pd.Series(dtype=str)
    ).apply(_norm_id)

    cols_siren = ["siren_ul", "siren_ref", "siren_ref_app"]
    df_sn["siren_retenu"] = df_sn.apply(
        lambda r: _pick_first_non_null(r, cols_siren), axis=1
    )
    df_sn["siren_retenu"] = df_sn["siren_retenu"].apply(_norm_id)
    df_sn["phase"] = pd.to_numeric(df_sn.get("phase"), errors="coerce")

    # ─── Filtrer aux validés des deux côtés ─────────────────────────────────
    df_eg_v = df_st[df_st["statut"].isin(VALIDES)].copy()
    df_ej_v = df_sn[df_sn["statut"].isin(VALIDES)].copy()

    # ─── Préparer la table EJ pour le merge ─────────────────────────────────
    cols_ej_keep = {
        "nmfinessej_stru_norm":   "nmfinessej_ej",       
        "siren_retenu":           "siren_ej_retenu",
        "statut":                 "statut_ej",
        "phase":                  "phase_ej",
    }
    cols_ej_optional = {
        "raisonsociale_stru":      "nom_ej",
        "nom_ul_retenu":           "nom_ul_retenu",
        "denominationUniteLegale": "denomination_ul",
        "cdcommune_stru":          "commune_ej",
        "nmsiren_stru":            "siren_finess_ej",
        "idstructure_stru":        "id_ej",
    }
    for col, rename in cols_ej_optional.items():
        if col in df_ej_v.columns:
            cols_ej_keep[col] = rename

    df_ej_for_merge = (
        df_ej_v[list(cols_ej_keep.keys())]
        .rename(columns=cols_ej_keep)
        .drop_duplicates("nmfinessej_ej", keep="first")
    )

    # ─── Préparer la table EG ───────────────────────────────────────────────
    cols_eg_keep = {
        "idstructure_stru":       "id_eg",
        "nmfinessej_stru_norm":   "nmfinessej_eg",  
        "nmfinessetab_stru":      "nmfinessetab_stru",
        "raisonsociale_stru":     "nom_eg",
        "cdcommune_stru":         "commune_eg",
        "nmsiret_stru":           "siret_finess_eg",
        "siret_retenu":           "siret_eg_retenu",
        "siren_from_siret":       "siren_du_siret_eg",
        "statut":                 "statut_eg",
        "phase":                  "phase_eg",
    }
    cols_eg_optional = {
        "nom_etab_retenu":        "nom_etab_retenu",
        "adresse_complete_etab":  "adresse_etab_sirene",
    }
    for col, rename in cols_eg_optional.items():
        if col in df_eg_v.columns:
            cols_eg_keep[col] = rename

    df_eg_for_merge = df_eg_v[list(cols_eg_keep.keys())].rename(columns=cols_eg_keep)

    # ─── Merge EG -> EJ (sur nmfinessej_stru des deux côtés) ────────────────
    df_couples = df_eg_for_merge.merge(
        df_ej_for_merge,
        left_on="nmfinessej_eg",
        right_on="nmfinessej_ej",
        how="left",
    )

    # ─── Classification ─────────────────────────────────────────────────────
    def _classer(row):
        id_ej_parent = row.get("nmfinessej_eg", "") or ""
        if not id_ej_parent:
            return "ORPHELIN"
        if pd.isna(row.get("statut_ej")):
            return "PARTIEL_EG"
        siren_eg = row.get("siren_du_siret_eg", "") or ""
        siren_ej = row.get("siren_ej_retenu", "") or ""
        if siren_eg and siren_ej and siren_eg == siren_ej:
            return "COHERENT"
        return "INCOHERENT"

    df_couples["statut_coherence"] = df_couples.apply(_classer, axis=1)

    # ─── EJ orphelins (validés sans EG validé associé) ──────────────────────
    ids_ej_avec_eg = set(
        df_couples[df_couples["statut_coherence"].isin(["COHERENT", "INCOHERENT"])]
        ["nmfinessej_eg"].dropna()
    )

    df_ej_orphelins_src = df_ej_v[
        ~df_ej_v["nmfinessej_stru_norm"].isin(ids_ej_avec_eg)
    ].copy()

    lignes_orphelins = []
    for _, ej in df_ej_orphelins_src.iterrows():
        id_finess_ej = _norm_id(ej.get("nmfinessej_stru"))
        ligne = {
            "id_eg":                None,
            "nmfinessej_eg":         id_finess_ej,
            "nmfinessetab_stru":    None,
            "nom_eg":               None,
            "commune_eg":           None,
            "siret_finess_eg":      None,
            "siret_eg_retenu":      None,
            "siren_du_siret_eg":    None,
            "statut_eg":            None,
            "phase_eg":             None,
            "nom_etab_retenu":      None,
            "adresse_etab_sirene":  None,
            "nmfinessej_ej":                id_finess_ej,
            "siren_ej_retenu":      ej.get("siren_retenu", ""),
            "statut_ej":            ej.get("statut", ""),
            "phase_ej":             ej.get("phase", ""),
            "nom_ej":               ej.get("raisonsociale_stru"),
            "nom_ul_retenu":        ej.get("nom_ul_retenu"),
            "denomination_ul":      ej.get("denominationUniteLegale"),
            "commune_ej":           ej.get("cdcommune_stru"),
            "siren_finess_ej":      ej.get("nmsiren_stru"),
            "id_interne_ej":        ej.get("idstructure_stru"),
            "statut_coherence":     "PARTIEL_EJ",
        }
        lignes_orphelins.append(ligne)

    df_orphelins = pd.DataFrame(lignes_orphelins) if lignes_orphelins else pd.DataFrame()

    df_vue_a = pd.concat([df_couples, df_orphelins], ignore_index=True)
    return df_vue_a


# ─── Synthèse par EJ ─────────────────────────────────────────────────────────

def synthese_par_ej(df_vue_a: pd.DataFrame) -> dict:
    """Synthèse au niveau EJ pour le bandeau de la vue A."""
    df_avec_match = df_vue_a[df_vue_a["statut_coherence"].isin(["COHERENT", "INCOHERENT"])]
    par_ej = df_avec_match.groupby("nmfinessej_eg")["statut_coherence"].apply(set)

    nb_ej_tous_coh   = sum(1 for s in par_ej if s == {"COHERENT"})
    nb_ej_avec_incoh = sum(1 for s in par_ej if "INCOHERENT" in s)

    nb_partiel_ej = (df_vue_a["statut_coherence"] == "PARTIEL_EJ").sum()
    nb_partiel_eg = (df_vue_a["statut_coherence"] == "PARTIEL_EG").sum()
    nb_orphelins  = (df_vue_a["statut_coherence"] == "ORPHELIN").sum()

    return {
        "EJ_avec_tous_EG_coherents":     nb_ej_tous_coh,
        "EJ_avec_au_moins_un_incoherent": nb_ej_avec_incoh,
        "EJ_sans_EG_valides_(PARTIEL_EJ)": int(nb_partiel_ej),
        "EG_sans_EJ_valide_(PARTIEL_EG)":  int(nb_partiel_eg),
        "EG_orphelins_sans_EJ_parent":     int(nb_orphelins),
    }


# ─── Synthèse globale Siretisation × Sirenisation ───────────────────────────

def synthese_globale(df_st_fusion: pd.DataFrame, df_sn_fusion: pd.DataFrame) -> pd.DataFrame:
    """
    Tableau de synthèse globale regroupant les compteurs siretisation et
    sirenisation par statut et par phase.

    Lignes : statuts (validés déclinés par phase + autres statuts globaux).
    Colonnes : Siretisation, Sirenisation.
    """
    statuts_valides = ["VALIDE_FORT", "VALIDE"]
    statuts_autres  = ["DOUTEUX", "REJETE", "SANS_CANDIDAT"]
    statuts_finess  = [("SANS_SIRET", "SANS_SIREN"),
                       ("SIRET_INCONNU", "SIREN_INCONNU")]

    def _compter(df, statut, phase=None):
        if "statut" not in df.columns:
            return 0
        m = (df["statut"] == statut)
        if phase is not None and "phase" in df.columns:
            m = m & (df["phase"] == phase)
        return int(m.sum())

    lignes = []

    # Validés par phase
    for statut in statuts_valides:
        for phase in (1, 2, 3):
            lignes.append({
                "Indicateur":   f"{statut} (Phase {phase})",
                "Siretisation": _compter(df_st_fusion, statut, phase),
                "Sirenisation": _compter(df_sn_fusion, statut, phase),
            })

    lignes.append({"Indicateur": "—", "Siretisation": "", "Sirenisation": ""})

    # Autres statuts (globaux)
    for statut in statuts_autres:
        lignes.append({
            "Indicateur":   statut,
            "Siretisation": _compter(df_st_fusion, statut),
            "Sirenisation": _compter(df_sn_fusion, statut),
        })

    # Statuts spécifiques au type
    for s_st, s_sn in statuts_finess:
        lignes.append({
            "Indicateur":   f"{s_st} / {s_sn}",
            "Siretisation": _compter(df_st_fusion, s_st),
            "Sirenisation": _compter(df_sn_fusion, s_sn),
        })

    lignes.append({"Indicateur": "—", "Siretisation": "", "Sirenisation": ""})

    # Totaux
    total_valides_st = sum(_compter(df_st_fusion, s) for s in statuts_valides)
    total_valides_sn = sum(_compter(df_sn_fusion, s) for s in statuts_valides)
    lignes.append({
        "Indicateur":   "TOTAL VALIDÉS",
        "Siretisation": total_valides_st,
        "Sirenisation": total_valides_sn,
    })
    lignes.append({
        "Indicateur":   "TOTAL TRAITÉS",
        "Siretisation": len(df_st_fusion),
        "Sirenisation": len(df_sn_fusion),
    })

    return pd.DataFrame(lignes)

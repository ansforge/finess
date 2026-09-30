"""Cohérence SIREN ↔ SIRET entre les deux pipelines."""
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

VALIDES = {"VALIDE_FORT", "VALIDE"}

MAP_ST = {
    "Valide_fort": "VALIDE_FORT", "Valide": "VALIDE",
    "Douteux": "DOUTEUX", "Rejeté": "REJETE",
    "Sans_SIRET": "SANS_SIRET", "SIRET_inconnu": "SIRET_INCONNU",
    "Sans_candidat": "SANS_CANDIDAT", "Non_fiable_APE": "NON_FIABLE_APE",
}
MAP_SN = {
    "Valide_fort": "VALIDE_FORT", "Valide": "VALIDE",
    "Douteux": "DOUTEUX", "Rejeté": "REJETE",
    "Sans_SIREN": "SANS_SIREN", "SIREN_inconnu": "SIREN_INCONNU",
    "Sans_candidat": "SANS_CANDIDAT",
}


# Chaque phase nomme differemment la colonne portant l'identifiant retenu : la
# phase 1 le tire de la jointure exacte, les phases 2 et 3 du candidat de rang 1.
# L'ordre suit celui des phases, les derniers noms servant de repli.
COLS_SIRET_RETENU = ["siret_etab", "siret_ref", "siret_ref_app",
                     "siret", "siret_norm_ege"]
COLS_SIREN_RETENU = ["siren_ul", "siren_ref", "siren_ref_app",
                     "siren", "siren_norm_pm"]


def _norm_id(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    return re.sub(r"\s", "", str(val).strip())


def _siren_from_siret(siret) -> str:
    s = _norm_id(siret)
    return s[:9] if len(s) >= 9 else ""


def _premiere_valeur(row, cols) -> str:
    for col in cols:
        val = row.get(col)
        if val is not None and not (isinstance(val, float) and pd.isna(val)):
            s = str(val).strip()
            if s:
                return s
    return ""


# ─── Fusion des fichiers de phase ────────────────────────────────────────────

def charger_et_fusionner_phases(chemin_p1, chemin_p2, chemin_p3,
                                type_pipeline: str, col_id: str) -> pd.DataFrame:
    """Fusionne les trois phases en cascade : tout le P1, puis du P2 ce qui n'y
    est pas validé, puis du P3 ce qui ne l'est ni en P1 ni en P2. Seul le rang 1
    est retenu pour les phases probabilistes."""
    mapping = MAP_ST if type_pipeline == "siretisation" else MAP_SN

    feuilles = pd.read_excel(chemin_p1, sheet_name=None, dtype=str)
    dfs = []
    for nom, sdf in feuilles.items():
        if nom.lower().startswith("synth"):
            continue
        sdf = sdf.copy()
        sdf["statut"] = mapping.get(nom, nom)
        sdf["phase"] = 1
        dfs.append(sdf)
    df_p1 = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

    def _rang1(chemin, feuille, phase):
        if chemin is None or not Path(chemin).exists():
            return pd.DataFrame()
        d = pd.read_excel(chemin, sheet_name=feuille, dtype=str)
        d["rang"] = pd.to_numeric(d["rang"], errors="coerce")
        d = d[d["rang"] == 1].copy()
        d["phase"] = phase
        # cote siretisation, le verdict de la structure tient compte du controle
        # d'activite : il peut differer du statut du candidat de rang 1
        if "statut_structure" in d.columns:
            d = d.drop(columns=["statut_candidat"], errors="ignore")
            d = d.rename(columns={"statut_structure": "statut"})
        elif "statut_candidat" in d.columns:
            d = d.rename(columns={"statut_candidat": "statut"})
        return d

    df_p2 = _rang1(chemin_p2, "Top5", 2)
    df_p3 = _rang1(chemin_p3, "Top3", 3)

    ids_v1 = set(df_p1[df_p1["statut"].isin(VALIDES)][col_id].dropna().astype(str))
    if len(df_p2):
        df_p2 = df_p2[~df_p2[col_id].astype(str).isin(ids_v1)].copy()
    ids_v2 = set(df_p2[df_p2["statut"].isin(VALIDES)][col_id].dropna().astype(str)) \
        if len(df_p2) else set()
    if len(df_p3):
        df_p3 = df_p3[~df_p3[col_id].astype(str).isin(ids_v1 | ids_v2)].copy()

    return pd.concat([d for d in (df_p1, df_p2, df_p3) if len(d)], ignore_index=True)


def charger_siretisation(p1, p2, p3) -> pd.DataFrame:
    return charger_et_fusionner_phases(p1, p2, p3, "siretisation", "NB_EgeId")


def charger_sirenisation(p1, p2, p3) -> pd.DataFrame:
    return charger_et_fusionner_phases(p1, p2, p3, "sirenisation", "NB_PmSmsseId")


# ─── Vue de cohérence ────────────────────────────────────────────────────────

def construire_vue_coherence(df_st: pd.DataFrame, df_sn: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par couple (PM, EGE) avec son verdict de cohérence."""
    df_st, df_sn = df_st.copy(), df_sn.copy()

    df_st["cle_pm"] = df_st.get("NB_PmSmsseId", pd.Series(dtype=str)).apply(_norm_id)
    df_st["siret_retenu"] = df_st.apply(
        lambda r: _premiere_valeur(r, COLS_SIRET_RETENU), axis=1
    ).apply(_norm_id)
    df_st["siren_du_siret"] = df_st["siret_retenu"].apply(_siren_from_siret)
    df_st["phase"] = pd.to_numeric(df_st.get("phase"), errors="coerce")

    df_sn["cle_pm"] = df_sn.get("NB_PmSmsseId", pd.Series(dtype=str)).apply(_norm_id)
    df_sn["siren_retenu"] = df_sn.apply(
        lambda r: _premiere_valeur(r, COLS_SIREN_RETENU), axis=1
    ).apply(_norm_id)
    df_sn["phase"] = pd.to_numeric(df_sn.get("phase"), errors="coerce")

    eg_v = df_st[df_st["statut"].isin(VALIDES)].copy()
    pm_v = df_sn[df_sn["statut"].isin(VALIDES)].copy()

    cols_pm = {"cle_pm": "cle_pm", "siren_retenu": "siren_pm_retenu",
               "statut": "statut_pm", "phase": "phase_pm"}
    for col, alias in {"TX_NumFinessPm": "finess_pm", "TX_DenominationPm": "nom_pm",
                       "nom_ul_retenu": "nom_ul_retenu", "TX_Siren": "siren_finess_pm",
                       "cdcommune_norm_pm": "commune_pm"}.items():
        if col in pm_v.columns:
            cols_pm[col] = alias
    pm_merge = (pm_v[list(cols_pm)].rename(columns=cols_pm)
                .drop_duplicates("cle_pm", keep="first"))

    cols_eg = {"NB_EgeId": "id_ege", "cle_pm": "cle_pm",
               "siret_retenu": "siret_ege_retenu", "siren_du_siret": "siren_du_siret_ege",
               "statut": "statut_ege", "phase": "phase_ege"}
    for col, alias in {"TX_NumFinessEge": "finess_ege", "TX_NomEgeLong": "nom_ege",
                       "nom_etab_retenu": "nom_etab_retenu", "TX_Siret": "siret_finess_ege",
                       "cdcommune_norm_ege": "commune_ege"}.items():
        if col in eg_v.columns:
            cols_eg[col] = alias
    eg_merge = eg_v[list(cols_eg)].rename(columns=cols_eg)

    couples = eg_merge.merge(pm_merge, on="cle_pm", how="left")

    def _classer(row):
        if not row.get("cle_pm"):
            return "ORPHELIN"
        if pd.isna(row.get("statut_pm")):
            return "PARTIEL_EG"
        a, b = row.get("siren_du_siret_ege", ""), row.get("siren_pm_retenu", "")
        return "COHERENT" if (a and b and a == b) else "INCOHERENT"

    couples["statut_coherence"] = couples.apply(_classer, axis=1)

    pm_avec_eg = set(couples[couples["statut_coherence"].isin(["COHERENT", "INCOHERENT"])]["cle_pm"])
    orphelins = pm_v[~pm_v["cle_pm"].isin(pm_avec_eg)].copy()

    if len(orphelins):
        lignes = pd.DataFrame({
            "id_ege": None, "cle_pm": orphelins["cle_pm"],
            "siret_ege_retenu": None, "siren_du_siret_ege": None,
            "statut_ege": None, "phase_ege": None,
            "siren_pm_retenu": orphelins["siren_retenu"],
            "statut_pm": orphelins["statut"], "phase_pm": orphelins["phase"],
            "statut_coherence": "PARTIEL_EJ",
        })
        for col, alias in {"TX_NumFinessPm": "finess_pm", "TX_DenominationPm": "nom_pm"}.items():
            if col in orphelins.columns:
                lignes[alias] = orphelins[col].values
        couples = pd.concat([couples, lignes], ignore_index=True)

    return couples


def synthese_par_pm(df_vue: pd.DataFrame) -> dict:
    """Synthèse au niveau personne morale."""
    avec_match = df_vue[df_vue["statut_coherence"].isin(["COHERENT", "INCOHERENT"])]
    par_pm = avec_match.groupby("cle_pm")["statut_coherence"].apply(set)
    return {
        "PM_avec_tous_EG_coherents": sum(1 for s in par_pm if s == {"COHERENT"}),
        "PM_avec_au_moins_un_incoherent": sum(1 for s in par_pm if "INCOHERENT" in s),
        "PM_sans_EG_valides_(PARTIEL_EJ)": int((df_vue["statut_coherence"] == "PARTIEL_EJ").sum()),
        "EG_sans_PM_valide_(PARTIEL_EG)": int((df_vue["statut_coherence"] == "PARTIEL_EG").sum()),
        "EG_orphelins_sans_PM": int((df_vue["statut_coherence"] == "ORPHELIN").sum()),
    }


def synthese_globale(df_st: pd.DataFrame, df_sn: pd.DataFrame) -> pd.DataFrame:
    """Compteurs par statut et par phase, pour les deux pipelines."""
    valides = ["VALIDE_FORT", "VALIDE"]
    autres = ["DOUTEUX", "REJETE", "SANS_CANDIDAT", "NON_FIABLE_APE"]
    specifiques = [("SANS_SIRET", "SANS_SIREN"), ("SIRET_INCONNU", "SIREN_INCONNU")]

    def compter(df, statut, phase=None):
        if "statut" not in df.columns:
            return 0
        m = df["statut"] == statut
        if phase is not None and "phase" in df.columns:
            m &= (df["phase"] == phase)
        return int(m.sum())

    lignes = []
    for statut in valides:
        for phase in (1, 2, 3):
            lignes.append({"Indicateur": f"{statut} (Phase {phase})",
                           "Siretisation": compter(df_st, statut, phase),
                           "Sirenisation": compter(df_sn, statut, phase)})
    lignes.append({"Indicateur": "—", "Siretisation": "", "Sirenisation": ""})
    for statut in autres:
        lignes.append({"Indicateur": statut,
                       "Siretisation": compter(df_st, statut),
                       "Sirenisation": compter(df_sn, statut)})
    for s_st, s_sn in specifiques:
        lignes.append({"Indicateur": f"{s_st} / {s_sn}",
                       "Siretisation": compter(df_st, s_st),
                       "Sirenisation": compter(df_sn, s_sn)})
    lignes.append({"Indicateur": "—", "Siretisation": "", "Sirenisation": ""})
    lignes.append({"Indicateur": "TOTAL VALIDÉS",
                   "Siretisation": sum(compter(df_st, s) for s in valides),
                   "Sirenisation": sum(compter(df_sn, s) for s in valides)})
    lignes.append({"Indicateur": "TOTAL TRAITÉS",
                   "Siretisation": len(df_st), "Sirenisation": len(df_sn)})
    return pd.DataFrame(lignes)


def decouper_par_phase(df_vue: pd.DataFrame) -> dict:
    """Découpe la vue de cohérence par couple de phases.

    Les couples cohérents sont répartis selon la phase qui a validé chaque côté :
    P1/P1, P2/P2, P3/P3, et mixtes quand les deux côtés n'ont pas été validés à
    la même phase.
    """
    df = df_vue.copy()
    df["_ph_pm"] = pd.to_numeric(df.get("phase_pm"), errors="coerce")
    df["_ph_ege"] = pd.to_numeric(df.get("phase_ege"), errors="coerce")

    coh = df[df["statut_coherence"] == "COHERENT"]
    memes = {p: coh[(coh["_ph_pm"] == p) & (coh["_ph_ege"] == p)] for p in (1, 2, 3)}
    deja = pd.concat(memes.values()).index
    mixtes = coh[~coh.index.isin(deja)]
    partiel = df[df["statut_coherence"].isin(["PARTIEL_EG", "PARTIEL_EJ", "ORPHELIN"])]

    def nettoyer(d):
        return d.drop(columns=["_ph_pm", "_ph_ege"], errors="ignore")

    return {
        "Coherent_P1": nettoyer(memes[1]),
        "Coherent_P2": nettoyer(memes[2]),
        "Coherent_P3": nettoyer(memes[3]),
        "Coherent_mixte": nettoyer(mixtes),
        "Incoherent": nettoyer(df[df["statut_coherence"] == "INCOHERENT"]),
        "Partiel_PM": nettoyer(partiel[partiel["statut_coherence"] == "PARTIEL_EJ"]),
        "Partiel_EGE": nettoyer(
            partiel[partiel["statut_coherence"].isin(["PARTIEL_EG", "ORPHELIN"])]),
    }


def synthese_par_phase(blocs: dict) -> tuple:
    """Deux tableaux : couples par catégorie, puis structures distinctes."""
    cles_coh = ("Coherent_P1", "Coherent_P2", "Coherent_P3", "Coherent_mixte")

    couples = pd.DataFrame([
        {"Categorie": "Coherent - phase 1", "Couples": len(blocs["Coherent_P1"])},
        {"Categorie": "Coherent - phase 2", "Couples": len(blocs["Coherent_P2"])},
        {"Categorie": "Coherent - phase 3", "Couples": len(blocs["Coherent_P3"])},
        {"Categorie": "Coherent - phases mixtes", "Couples": len(blocs["Coherent_mixte"])},
        {"Categorie": "TOTAL COHERENTS", "Couples": sum(len(blocs[k]) for k in cles_coh)},
        {"Categorie": "Incoherent", "Couples": len(blocs["Incoherent"])},
        {"Categorie": "Partiel PM (PM seule validee)", "Couples": len(blocs["Partiel_PM"])},
        {"Categorie": "Partiel EGE (EGE seul valide)", "Couples": len(blocs["Partiel_EGE"])},
    ])

    def nb_pm(d):
        return d["cle_pm"].dropna().nunique() if "cle_pm" in d else 0

    tous = pd.concat([blocs[k] for k in cles_coh], ignore_index=True)
    structures = pd.DataFrame([
        {"Categorie": "PM coherentes en phase 1", "Distinctes": nb_pm(blocs["Coherent_P1"])},
        {"Categorie": "PM coherentes en phase 2", "Distinctes": nb_pm(blocs["Coherent_P2"])},
        {"Categorie": "PM coherentes en phase 3", "Distinctes": nb_pm(blocs["Coherent_P3"])},
        {"Categorie": "PM coherentes phases mixtes", "Distinctes": nb_pm(blocs["Coherent_mixte"])},
        {"Categorie": "TOTAL PM coherentes", "Distinctes": nb_pm(tous)},
        {"Categorie": "PM avec au moins un EGE incoherent", "Distinctes": nb_pm(blocs["Incoherent"])},
        {"Categorie": "PM sans EGE valide", "Distinctes": len(blocs["Partiel_PM"])},
        {"Categorie": "EGE sans PM validee", "Distinctes": len(blocs["Partiel_EGE"])},
    ])
    return couples, structures

"""Contrôle du domaine d'activité des candidats de siretisation."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.scoring import normaliser_ape

NON_FIABLE_APE = "NON_FIABLE_APE"
VALIDES = ("VALIDE_FORT", "VALIDE")

MOTIF_IDENTIQUE = "APE_IDENTIQUE"
MOTIF_DOMAINE = "DOMAINE_FINESS"
MOTIF_AUCUN = "AUCUN_CANDIDAT_ACCEPTABLE"
MOTIF_SANS_OBJET = ""   # aucun candidat validé au score : l'activité n'a rien tranché

# Le domaine repose sur le sens métier, pas sur la fréquence d'apparition dans
DIVISIONS_COEUR = {
    "86",   # activités pour la santé humaine
    "87",   # hébergement médico-social et social
    "88",   # action sociale sans hébergement
}

CODES_COEUR = {
    "9499Z",                              # autres organisations associatives
    "8411Z", "8412Z", "8425Z",            # administration publique
    "8430A", "8430B",                     # sécurité sociale
    "8559A", "8559B",                     # formation continue, autres enseignements
    "8531Z", "8532Z", "8541Z", "8542Z",   # enseignement (IFSI, IFAS, écoles)
    "4773Z", "4774Z",                     # officines, matériel médical
    "9412Z",                              # organisations professionnelles
    "9609Z",                              # autres services personnels
}

# Écartés même s'ils apparaissent dans FINESS : fonctions support, patrimoine,
# services généraux. Ils ne caractérisent pas l'activité exercée.
CODES_EXCLUS = {
    "6820A", "6820B", "6810Z", "6832A", "6832B",   # immobilier
    "6619A", "6619B", "6511Z", "6512Z",            # patrimoine, assurance
    "7010Z", "7022Z", "7420Z",                     # holdings, conseil
    "9602A", "9602B",                              # coiffure, soins de beauté
    "8121Z", "8122Z", "8129A",                     # nettoyage
    "8219Z", "8299Z",                              # services de bureau
    "5590Z", "7729Z", "7739Z", "4646Z",            # hébergement générique, location
}


def est_domaine_finess(code_ape) -> bool:
    """Le code relève-t-il du sanitaire, du social ou du médico-social ?

    L'exclusion l'emporte sur l'appartenance à une division cœur : une SCI qui
    détient les murs d'une clinique porte un code immobilier, ce qui n'en fait
    pas un établissement de santé.
    """
    code = normaliser_ape(code_ape)
    if not code:
        return False
    if code in CODES_EXCLUS:
        return False
    if code[:2] in DIVISIONS_COEUR:
        return True
    return code in CODES_COEUR


def appliquer_controle(df_topn: pd.DataFrame, col_id: str, col_ape_candidat: str,
                       col_ape_structure: str = "ape_referentiel",
                       col_statut: str = "statut_candidat",
                       col_rang: str = "rang") -> pd.DataFrame:
    """Retient, par structure, le meilleur candidat validé et acceptable.

    Parcourt les candidats par rang croissant et ne considère que ceux validés
    par le score. Parmi eux, l'égalité exacte d'APE prime sur l'appartenance au
    domaine, et à règle égale c'est le mieux classé qui gagne.

    Une structure sans APE au référentiel est jugée sur le seul domaine.

    Colonnes ajoutées, sur chaque ligne :
        ape_finess, ape_candidat, ape_identique, ape_dans_domaine,
        ape_acceptable, candidat_retenu
    et sur la ligne de rang 1 seulement :
        rang_retenu, motif_ape, statut_structure
    """
    lignes = []

    for _, groupe in df_topn.groupby(col_id, sort=False):
        groupe = groupe.sort_values(col_rang)

        ape_structure = ""
        if col_ape_structure in groupe.columns:
            ape_structure = normaliser_ape(groupe[col_ape_structure].iloc[0])

        apes = groupe[col_ape_candidat].map(normaliser_ape)
        identiques = bool(ape_structure) & apes.eq(ape_structure) & apes.ne("")
        domaine = groupe[col_ape_candidat].map(est_domaine_finess)
        acceptables = identiques | domaine
        valides = groupe[col_statut].isin(VALIDES)

        candidats = valides & identiques
        if candidats.any():
            index_retenu, motif = candidats.idxmax(), MOTIF_IDENTIQUE
        else:
            candidats = valides & domaine
            if candidats.any():
                index_retenu, motif = candidats.idxmax(), MOTIF_DOMAINE
            else:
                index_retenu = None
                motif = MOTIF_AUCUN if valides.any() else MOTIF_SANS_OBJET

        if index_retenu is not None:
            rang_retenu = groupe.loc[index_retenu, col_rang]
            statut_structure = groupe.loc[index_retenu, col_statut]
        else:
            rang_retenu = None
            # le score validait, l'activite l'en empeche : statut distinct.
            # sinon la structure garde le verdict de son rang 1.
            statut_structure = (NON_FIABLE_APE if valides.any()
                                else groupe[col_statut].iloc[0])

        for position, (index, candidat) in enumerate(groupe.iterrows()):
            ligne = candidat.to_dict()
            ligne["ape_finess"] = ape_structure
            ligne["ape_candidat"] = apes.loc[index]
            ligne["ape_identique"] = bool(identiques.loc[index])
            ligne["ape_dans_domaine"] = bool(domaine.loc[index])
            ligne["ape_acceptable"] = bool(acceptables.loc[index])
            ligne["candidat_retenu"] = index == index_retenu
            ligne["rang_retenu"] = rang_retenu if position == 0 else None
            ligne["motif_ape"] = motif if position == 0 else ""
            ligne["statut_structure"] = statut_structure if position == 0 else ""
            lignes.append(ligne)

    return pd.DataFrame(lignes)


def rapport(df: pd.DataFrame, col_id: str, col_statut: str = "statut_candidat",
            col_rang: str = "rang") -> pd.DataFrame:
    """Effet du contrôle : ce que le score validait, ce que l'activité confirme."""
    decisions = df[df["statut_structure"] != ""]
    rang1 = df[df[col_rang] == 1]

    valides_score = int(rang1[col_statut].isin(VALIDES).sum())
    valides_final = int(decisions["statut_structure"].isin(VALIDES).sum())
    bloquees = int((decisions["statut_structure"] == NON_FIABLE_APE).sum())
    remplaces = int(((decisions["rang_retenu"].notna())
                     & (decisions["rang_retenu"] != 1)).sum())

    lignes = [
        {"Indicateur": "Structures traitées", "Nombre": len(decisions)},
        {"Indicateur": "Validées par le score au rang 1", "Nombre": valides_score},
        {"Indicateur": "—", "Nombre": ""},
        {"Indicateur": "Validées après contrôle d'activité", "Nombre": valides_final},
        {"Indicateur": "  dont candidat de rang 1 conservé",
         "Nombre": valides_final - remplaces},
        {"Indicateur": "  dont candidat remplacé", "Nombre": remplaces},
        {"Indicateur": "Bloquées — NON_FIABLE_APE", "Nombre": bloquees},
        {"Indicateur": "—", "Nombre": ""},
        {"Indicateur": "  retenues sur APE identique",
         "Nombre": int((decisions["motif_ape"] == MOTIF_IDENTIQUE).sum())},
        {"Indicateur": "  retenues sur le domaine",
         "Nombre": int((decisions["motif_ape"] == MOTIF_DOMAINE).sum())},
    ]
    return pd.DataFrame(lignes)

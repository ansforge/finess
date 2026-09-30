"""Référentiel des autorités d'enregistrement FINESS et résolution des couples
(catégorie d'établissement, département) en autorité compétente."""
from pathlib import Path

import pandas as pd

RESOLU = "RESOLU"
A_ARBITRER = "A_ARBITRER"
NON_DETERMINEE = "NON_DETERMINEE"

RESOLVABLE = "RESOLVABLE"
SANS_AUTORITE = "SANS_AUTORITE"
MULTI_AUTORITES = "MULTI_AUTORITES"

COLONNES_ROUTAGE = ["autorite_statut", "autorite_code", "autorite_candidats", "autorite_motif"]

REGION_IDF = "11"

# Familles d'autorité déduites du domaine de la catégorie. Vérifié sur le
# référentiel : Sanitaire est ARS à 78/80, Médico-social à 51/55, Social relève
# des solidarités à 41/42, Formation à 4/4.
FAMILLE_ARS = "ARS"
FAMILLE_SOLIDARITES = "SOLIDARITES"

DOMAINE_FAMILLE = {
    "Sanitaire": FAMILLE_ARS,
    "Médico-social": FAMILLE_ARS,
    "Social": FAMILLE_SOLIDARITES,
    "Formation": FAMILLE_SOLIDARITES,
}

_DEPTS_PAR_REGION = {
    "11": ["75", "77", "78", "91", "92", "93", "94", "95"],
    "24": ["18", "28", "36", "37", "41", "45"],
    "27": ["21", "25", "39", "58", "70", "71", "89", "90"],
    "28": ["14", "27", "50", "61", "76"],
    "32": ["02", "59", "60", "62", "80"],
    "44": ["08", "10", "51", "52", "54", "55", "57", "67", "68", "88"],
    "52": ["44", "49", "53", "72", "85"],
    "53": ["22", "29", "35", "56"],
    "75": ["16", "17", "19", "23", "24", "33", "40", "47", "64", "79", "86", "87"],
    "76": ["09", "11", "12", "30", "31", "32", "34", "46", "48", "65", "66", "81", "82"],
    "84": ["01", "03", "07", "15", "26", "38", "42", "43", "63", "69", "73", "74"],
    "93": ["04", "05", "06", "13", "83", "84"],
    "94": ["2A", "2B", "20"],
}

# Codes du référentiel des autorités, distincts des codes région INSEE.
# Saint-Barthélemy (977) et Saint-Martin (978) relèvent de l'ARS Guadeloupe :
# rattachement confirmé par la MOA.
DEPT_REGION_OM = {
    "971": "01", "977": "01", "978": "01",
    "972": "02",
    "973": "03",
    "974": "05",
    "976": "06",
}

DEPT_AGENCE_TERRITORIALE = {"975": "AT-975"}

DEPT_REGION = {d: reg for reg, depts in _DEPTS_PAR_REGION.items() for d in depts}
DEPT_REGION.update(DEPT_REGION_OM)

REGIONS_OM = set(DEPT_REGION_OM.values())

# Codes normés du J359 : en Outre-mer l'autorité des solidarités est une DEETS,
# et le code de l'hébergement et du logement en Île-de-France est DRHIL-11.
# La table Gestionnaire de FINESS+ écrit DRIHL-11 et des DREETS sur les régions
# ultramarines, ce qui ne suit pas le référentiel ; normaliser_autorite() ramène
# ces valeurs vers les codes normés.
PREFIXE_SOLIDARITES_OM = "DEETS"
CODE_DRHIL = "DRHIL-11"

LIBELLES_REGION = {
    "01": "Guadeloupe",
    "02": "Martinique",
    "03": "Guyane",
    "05": "La Réunion",
    "06": "Mayotte",
    "11": "Île-de-France",
    "24": "Centre-Val de Loire",
    "27": "Bourgogne-Franche-Comté",
    "28": "Normandie",
    "32": "Hauts-de-France",
    "44": "Grand Est",
    "52": "Pays de la Loire",
    "53": "Bretagne",
    "75": "Nouvelle-Aquitaine",
    "76": "Occitanie",
    "84": "Auvergne-Rhône-Alpes",
    "93": "Provence-Alpes-Côte d'Azur",
    "94": "Corse",
    "975": "Saint-Pierre-et-Miquelon",
}

# Valeurs sentinelles du DWH, présentes sur toutes les colonnes de nomenclature.
SENTINELLES = {"non pertinent", "non rapproche", "non rapproché",
               "non renseigne", "non renseigné", "-1", "-2", "-3"}

# L'ANS n'est pas une autorité territoriale mais l'agence elle-même. Elle est
# conservée telle quelle quand elle est déclarée dans FINESS+.
CODE_ANS = "ANS"


def extraire_departement(code_commune) -> str:
    """Département d'un code commune INSEE, sur 3 caractères en Outre-mer et 2 sinon."""
    if code_commune is None or pd.isna(code_commune):
        return ""
    code = str(code_commune).strip().upper().replace(" ", "")
    if not code:
        return ""
    return code[:3] if code[:2] in ("97", "98") else code[:2]


def normaliser_autorite(valeur) -> str:
    """Autorité déclarée dans FINESS+, ramenée au code normé du J359.

    Renvoie une chaîne vide pour les sentinelles du DWH et les valeurs absentes.
    La base écrit DRIHL-11 au lieu de DRHIL-11, et des DREETS sur les régions
    ultramarines là où le référentiel attend des DEETS. La Corse (94) n'est pas
    ultramarine : DREETS-94 est conforme et n'est pas converti.
    """
    if valeur is None or (isinstance(valeur, float) and pd.isna(valeur)):
        return ""
    code = str(valeur).strip()
    if not code or code.lower() in SENTINELLES:
        return ""

    code = code.replace("DRIHL-", "DRHIL-")
    if code.startswith("DREETS-") and code.split("-", 1)[1] in REGIONS_OM:
        code = "DEETS-" + code.split("-", 1)[1]
    return code


def charger_referentiel(chemin) -> pd.DataFrame:
    """Charge et normalise le fichier MOA des catégories d'établissements."""
    chemin = Path(chemin)
    if chemin.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        brut = pd.read_excel(chemin, skiprows=2, dtype=str)
    else:
        brut = pd.read_csv(chemin, sep=";", encoding="cp1252", skiprows=2, dtype=str)

    brut = brut.loc[:, ~brut.columns.astype(str).str.startswith("Unnamed")]
    brut.columns = [str(c).strip() for c in brut.columns]
    brut = brut.dropna(subset=["Catégorie"])

    ref = pd.DataFrame({
        "code_categorie": brut["Catégorie"].str.strip().str.zfill(3),
        "domaine": brut["Domaine"].str.strip(),
        "libelle_court": brut["Libellé court"].str.strip(),
        "libelle_long": brut["Libellé long"].str.strip(),
        "ars": brut["ARS"].notna().astype(int),
        "dreets": brut["DREETS"].notna().astype(int),
        "drhil": brut["DRHIL"].notna().astype(int),
        "autorite_principale_source": brut["Principale"].fillna("").str.strip(),
    })
    ref["statut_referentiel"] = ref.apply(_statut_referentiel, axis=1)
    ref["famille"] = ref["domaine"].map(DOMAINE_FAMILLE).fillna("")

    doublons = ref.loc[ref["code_categorie"].duplicated(), "code_categorie"]
    if not doublons.empty:
        raise ValueError(f"Codes catégorie en doublon : {sorted(doublons)}")

    return ref.sort_values("code_categorie").set_index("code_categorie")


def _statut_referentiel(ligne) -> str:
    if ligne["ars"] + ligne["dreets"] + ligne["drhil"] == 0:
        return SANS_AUTORITE
    if ligne["ars"] and (ligne["dreets"] or ligne["drhil"]):
        return MULTI_AUTORITES
    return RESOLVABLE


def _code_solidarites(region: str) -> str:
    prefixe = PREFIXE_SOLIDARITES_OM if region in REGIONS_OM else "DREETS"
    return f"{prefixe}-{region}"


def code_famille(famille: str, region: str) -> str:
    """Code d'autorité d'une famille sur une région donnée."""
    if famille == FAMILLE_ARS:
        return f"ARS-{region}"
    if famille == FAMILLE_SOLIDARITES:
        return CODE_DRHIL if region == REGION_IDF else _code_solidarites(region)
    return ""


def _non_determinee(motif: str) -> dict:
    return {"autorite_statut": NON_DETERMINEE, "autorite_code": "",
            "autorite_candidats": "", "autorite_motif": motif}


def resoudre(code_categorie, departement, referentiel: pd.DataFrame) -> dict:
    """Résout un couple (catégorie, département) et retourne les colonnes de routage."""
    dept = "" if departement is None or pd.isna(departement) else str(departement).strip().upper()
    if not dept:
        return _non_determinee("departement_absent")

    if dept in DEPT_AGENCE_TERRITORIALE:
        return {"autorite_statut": RESOLU, "autorite_code": DEPT_AGENCE_TERRITORIALE[dept],
                "autorite_candidats": "", "autorite_motif": ""}

    region = DEPT_REGION.get(dept)
    if region is None:
        return _non_determinee("departement_hors_perimetre")

    cat = "" if code_categorie is None or pd.isna(code_categorie) else str(code_categorie).strip().zfill(3)
    if not cat:
        return _non_determinee("categorie_absente")
    if cat not in referentiel.index:
        return _non_determinee("categorie_hors_referentiel")

    ligne = referentiel.loc[cat]

    if ligne["statut_referentiel"] == SANS_AUTORITE:
        hypothese = f"ARS-{region}" if "ARS" in ligne["autorite_principale_source"].upper() else ""
        return {"autorite_statut": A_ARBITRER, "autorite_code": "",
                "autorite_candidats": hypothese, "autorite_motif": "categorie_sans_autorite"}

    if ligne["statut_referentiel"] == MULTI_AUTORITES:
        candidats = []
        if ligne["ars"]:
            candidats.append(f"ARS-{region}")
        if ligne["drhil"] and region == REGION_IDF:
            candidats.append(CODE_DRHIL)
        elif ligne["dreets"]:
            candidats.append(_code_solidarites(region))
        return {"autorite_statut": A_ARBITRER, "autorite_code": "",
                "autorite_candidats": "|".join(candidats),
                "autorite_motif": "categorie_multi_autorites"}

    if ligne["ars"]:
        code = f"ARS-{region}"
    elif ligne["drhil"] and region == REGION_IDF:
        code = CODE_DRHIL
    else:
        code = _code_solidarites(region)

    return {"autorite_statut": RESOLU, "autorite_code": code,
            "autorite_candidats": "", "autorite_motif": ""}


def affecter(df: pd.DataFrame, referentiel: pd.DataFrame,
             col_categorie: str, col_departement: str) -> pd.DataFrame:
    """Ajoute les colonnes de routage à un DataFrame de structures."""
    resultats = [resoudre(cat, dept, referentiel)
                 for cat, dept in zip(df[col_categorie], df[col_departement])]
    routage = pd.DataFrame(resultats, index=df.index)
    return df.drop(columns=[c for c in COLONNES_ROUTAGE if c in df.columns]).join(routage)


def majorite_famille(familles) -> tuple:
    """Famille majoritaire en valeur absolue parmi les EGE fils d'une PM.

    Seuls les fils dont la catégorie a un domaine connu votent. Une majorité
    stricte est exigée : sur deux fils de familles différentes, aucune ne
    l'emporte et la PM part en arbitrage.

    Retourne (famille, nb_votes, nb_votants). Famille vide si pas de majorité.
    """
    votes = [f for f in familles if f]
    if not votes:
        return "", 0, 0

    compte = pd.Series(votes).value_counts()
    famille, n = compte.index[0], int(compte.iloc[0])
    return (famille, n, len(votes)) if n * 2 > len(votes) else ("", n, len(votes))

"""Contrôle qualité des numéros de téléphone FINESS (EG/EJ).

On nettoie le numéro puis on le classe en un seul passage (premier test qui matche).
Catégories : MANQUANT, ANOMALIE_CRITIQUE, SURTAXE, MOBILE, INCOHERENCE_GEO,
DOUBLON, VALIDE. Les signaux faibles (mobile, géo) restent informatifs.

Depuis le 01/01/2023 les contraintes géographiques des numéros 01-05 sont levées
(portabilité nationale) : INCOHERENCE_GEO est une heuristique, pas une erreur.
"""

import re
import pandas as pd


PLACEHOLDERS_TEXTE = {
    "", "nr", "n/a", "na", "neant", "néant", "inconnu", "aucun",
    "non renseigne", "non renseignée", "non renseigné", "nc", "xxx", "-", "0",
}

PREFIXES_SURTAXE = {"081", "082", "089"}
PREFIXES_MOBILE = {"06", "07"}
PREFIXES_GEO = {"01", "02", "03", "04", "05"}

NIVEAU = {
    "VALIDE": 0,
    "ANOMALIE_CRITIQUE": 1,
    "SURTAXE": 2, "MOBILE": 2, "INCOHERENCE_GEO": 2, "DOUBLON": 2,
    "MANQUANT": None,
}

# Département -> zone de numérotation (répartition ARCEP des 5 zones par région,
# plan national déc. 2018-0881). DOM : Réunion/Mayotte -> 02 ; Antilles-Guyane -> 05.
DEPT_ZONE = {}


def _z(zone, departements):
    for d in departements:
        DEPT_ZONE[d] = zone


_z("01", ["75", "77", "78", "91", "92", "93", "94", "95"])
_z("02", ["22", "29", "35", "56", "18", "28", "36", "37", "41", "45",
          "14", "27", "50", "61", "76", "44", "49", "53", "72", "85",
          "974", "976"])
_z("03", ["21", "25", "39", "58", "70", "71", "89", "90",
          "08", "10", "51", "52", "54", "55", "57", "67", "68", "88",
          "02", "59", "60", "62", "80"])
_z("04", ["01", "03", "07", "15", "26", "38", "42", "43", "63", "69", "73", "74",
          "2A", "2B", "04", "05", "06", "13", "83", "84",
          "11", "30", "34", "48", "66"])
_z("05", ["16", "17", "19", "23", "24", "33", "40", "47", "64", "79", "86", "87",
          "09", "12", "31", "32", "46", "65", "81", "82",
          "971", "972", "973"])


def clean_phone(raw) -> str:
    """Format national '0XXXXXXXXX' (chiffres seuls). '' si vide/sans chiffre."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return ""
    s = str(raw).strip()
    if s == "" or s.lower() in PLACEHOLDERS_TEXTE:
        return ""
    s = s.replace("(0)", "")
    s = re.sub(r"[^0-9+]", "", s)
    if s.startswith("0033"):
        s = "0" + s[4:]
    elif s.startswith("+33"):
        s = "0" + s[3:]
    return s


def extract_departement(cdcommune) -> str | None:
    """Département depuis un code commune INSEE (Corse 2A/2B, DOM 97x, zfill)."""
    if cdcommune is None or (isinstance(cdcommune, float) and pd.isna(cdcommune)):
        return None
    s = str(cdcommune).strip()
    if s.endswith(".0"):
        s = s[:-2]
    if s == "":
        return None
    up = s.upper()
    if up.startswith("2A") or up.startswith("2B"):
        return up[:2]
    s = re.sub(r"\D", "", s)
    if s == "":
        return None
    s = s.zfill(5)
    if s[:2] in ("97", "98"):
        return s[:3]
    return s[:2]


def departement_to_zone(dept) -> str | None:
    if dept is None:
        return None
    return DEPT_ZONE.get(dept)


def is_fake_empty(cleaned: str) -> bool:
    return cleaned != "" and set(cleaned) == {"0"}


def is_bogus_pattern(num: str):
    if len(set(num[1:])) == 1:
        return True, "chiffres répétés"
    if num[:2] * 5 == num:
        return True, "bloc répété"
    if num == "0123456789":
        return True, "séquence numérique"
    paires = [num[i:i + 2] for i in range(0, 10, 2)]
    if all(int(paires[k + 1]) - int(paires[k]) == 1 for k in range(len(paires) - 1)):
        return True, "séquence par paires"
    return False, ""


def classify_phone(raw, cdcommune=None) -> dict:
    """Classe un numéro (hors doublon), premier test qui matche."""
    cleaned = clean_phone(raw)
    zone_numero = cleaned[:2] if len(cleaned) >= 2 and cleaned[0] == "0" else None
    dept = extract_departement(cdcommune)
    zone_attendue = departement_to_zone(dept)
    base = {
        "telephone_clean": cleaned,
        "departement": dept,
        "zone_numero": zone_numero,
        "zone_attendue": zone_attendue,
    }

    if cleaned == "":
        return {**base, "categorie": "MANQUANT", "motif": "vide ou non renseigné"}
    if is_fake_empty(cleaned):
        return {**base, "categorie": "MANQUANT", "motif": "faux vide (zéros)"}

    if not cleaned.isdigit():
        return {**base, "categorie": "ANOMALIE_CRITIQUE", "motif": "caractères non numériques résiduels"}
    if len(cleaned) != 10:
        return {**base, "categorie": "ANOMALIE_CRITIQUE", "motif": f"longueur {len(cleaned)} != 10"}
    if cleaned[0] != "0" or cleaned[1] == "0":
        return {**base, "categorie": "ANOMALIE_CRITIQUE", "motif": f"préfixe invalide ({cleaned[:2]})"}

    bidon, motif = is_bogus_pattern(cleaned)
    if bidon:
        return {**base, "categorie": "ANOMALIE_CRITIQUE", "motif": motif}

    p2, p3 = cleaned[:2], cleaned[:3]
    if p3 in PREFIXES_SURTAXE:
        return {**base, "categorie": "SURTAXE", "motif": f"08 payant ({p3})"}
    if p2 in PREFIXES_MOBILE:
        return {**base, "categorie": "MOBILE", "motif": "mobile (06/07)"}
    if p2 in PREFIXES_GEO and zone_attendue is not None and p2 != zone_attendue:
        return {**base, "categorie": "INCOHERENCE_GEO",
                "motif": f"numéro zone {p2}, commune zone {zone_attendue}"}

    return {**base, "categorie": "VALIDE", "motif": ""}


def analyser_telephones(df: pd.DataFrame,
                        col_tel: str = "telephone_stru",
                        col_commune: str = "cdcommune_stru") -> pd.DataFrame:
    df = df.copy()
    commune = df[col_commune] if col_commune in df.columns else pd.Series([None] * len(df), index=df.index)
    res = pd.DataFrame([classify_phone(t, c) for t, c in zip(df[col_tel], commune)], index=df.index)
    df["telephone_clean"] = res["telephone_clean"]
    df["departement"] = res["departement"]
    df["zone_numero"] = res["zone_numero"]
    df["zone_attendue"] = res["zone_attendue"]
    df["categorie"] = res["categorie"]
    df["motif"] = res["motif"]
    df["niveau"] = df["categorie"].map(NIVEAU)
    return df


def marquer_doublons(df: pd.DataFrame,
                     col_tel_clean: str = "telephone_clean",
                     col_id: str = "idstructure_stru") -> pd.DataFrame:
    """Numéros exploitables partagés par plusieurs structures -> catégorie DOUBLON.

    Cherchés uniquement hors MANQUANT/ANOMALIE_CRITIQUE : un doublon n'écrase
    jamais une anomalie critique ni un manquant.
    """
    df = df.copy()
    exploitable = ~df["categorie"].isin(["MANQUANT", "ANOMALIE_CRITIQUE"])
    nums = df.loc[exploitable, col_tel_clean]
    n_par_num = nums.groupby(nums).transform("size")
    df["nb_structures_meme_tel"] = 1
    df.loc[exploitable, "nb_structures_meme_tel"] = n_par_num
    df["nb_structures_meme_tel"] = df["nb_structures_meme_tel"].fillna(1).astype(int)
    df["est_doublon"] = df["nb_structures_meme_tel"] > 1

    masque = df["est_doublon"]
    df.loc[masque, "categorie"] = "DOUBLON"
    df.loc[masque, "motif"] = df.loc[masque, "nb_structures_meme_tel"].apply(
        lambda n: f"numéro partagé par {n} structures distinctes — vérifier si intentionnel"
    )
    df["niveau"] = df["categorie"].map(NIVEAU)
    return df

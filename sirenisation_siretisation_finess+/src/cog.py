"""Validation des codes commune sur la table de passage INSEE."""
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

VALIDE = "VALIDE"
ARRONDISSEMENT = "ARRONDISSEMENT"
CORRIGE = "CORRIGE"
AMBIGU = "AMBIGU"
HORS_COG = "HORS_COG"
INCONNU = "INCONNU"
ABSENT = "ABSENT"

STATUTS = [VALIDE, ARRONDISSEMENT, CORRIGE, AMBIGU, HORS_COG, INCONNU, ABSENT]

COLONNES_COG = ["cog_code_origine", "cog_code_retenu", "cog_statut",
                "cog_successeurs", "cog_libelle", "cog_anomalie"]

# Communes à arrondissements municipaux : les codes ARM ne figurent pas dans la
ARRONDISSEMENTS = {
    "751": "75056",   # Paris
    "693": "69123",   # Lyon
    "132": "13055",   # Marseille
}

# Saint-Pierre-et-Miquelon, Saint-Barthélemy, Saint-Martin et les collectivités
# du Pacifique sont hors du champ de la table, sans être pour autant erronés.
PREFIXES_HORS_COG = ("97", "98")


def normaliser_code_commune(valeur) -> str:
    """Code commune sur 5 caractères, en préservant les codes corses.

    Contrairement à la normalisation du pipeline principal, qui supprime tout
    caractère non numérique, celle-ci conserve le A et le B de la Corse :
    `2A004` y perdait sa lettre et devenait `02004`, soit un code de l'Aisne.
    """
    if valeur is None or (isinstance(valeur, float) and pd.isna(valeur)):
        return ""
    code = str(valeur).strip().upper().replace(" ", "")
    if not code or code.lower() in ("nan", "none"):
        return ""
    code = re.sub(r"[^0-9AB]", "", code)
    return code.zfill(5) if code else ""


def extraire_departement(code_commune) -> str:
    """Département d'un code commune : 3 caractères en Outre-mer, 2 sinon."""
    code = str(code_commune or "").strip().upper()
    if not code:
        return ""
    return code[:3] if code[:2] in ("97", "98") else code[:2]


def charger_table_passage(chemin) -> pd.DataFrame:
    """Charge la table de passage INSEE.

    L'en-tête réel est en sixième ligne, les cinq premières portant le titre et
    la source. Les trois colonnes utiles sont CODGEO_INI, CODGEO_2026 et
    LIBGEO_2026.
    """
    chemin = Path(chemin)
    if chemin.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        brut = pd.read_excel(chemin, sheet_name="Table de passage",
                             skiprows=5, dtype=str)
    else:
        brut = pd.read_csv(chemin, sep=";", skiprows=5, dtype=str)

    brut.columns = [str(c).strip() for c in brut.columns]
    manquantes = {"CODGEO_INI", "CODGEO_2026"} - set(brut.columns)
    if manquantes:
        raise KeyError(f"Colonnes absentes de la table de passage : {sorted(manquantes)}. "
                       f"Colonnes lues : {list(brut.columns)}")

    table = brut[["CODGEO_INI", "CODGEO_2026", "LIBGEO_2026"]].copy()
    for colonne in ("CODGEO_INI", "CODGEO_2026"):
        table[colonne] = table[colonne].astype(str).str.strip().str.upper()
    table = table[(table["CODGEO_INI"] != "") & (table["CODGEO_2026"] != "")]

    print(f"Table de passage : {len(table):,} correspondances")
    print(f"   codes initiaux distincts : {table['CODGEO_INI'].nunique():,}")
    print(f"   communes actives en 2026 : {table['CODGEO_2026'].nunique():,}")
    return table.reset_index(drop=True)


def construire_index(table: pd.DataFrame) -> dict:
    """Prépare les structures de recherche à partir de la table de passage."""
    actifs = set(table["CODGEO_2026"])
    successeurs = table.groupby("CODGEO_INI")["CODGEO_2026"].apply(list).to_dict()
    libelles = dict(zip(table["CODGEO_2026"], table["LIBGEO_2026"]))

    disparus = {c: s for c, s in successeurs.items() if c not in actifs}
    uniques = sum(1 for s in disparus.values() if len(s) == 1)
    print(f"   codes disparus : {len(disparus):,}, dont {uniques:,} à successeur unique")

    return {"actifs": actifs, "successeurs": successeurs, "libelles": libelles}


def resoudre(code, index: dict) -> dict:
    """Statut d'un code commune et code à retenir."""
    code = normaliser_code_commune(code)

    if not code:
        return {"cog_code_retenu": "", "cog_statut": ABSENT,
                "cog_successeurs": "", "cog_libelle": ""}

    if code in index["actifs"]:
        return {"cog_code_retenu": code, "cog_statut": VALIDE,
                "cog_successeurs": "", "cog_libelle": index["libelles"].get(code, "")}

    rattachement = ARRONDISSEMENTS.get(code[:3])
    if rattachement and rattachement in index["actifs"]:
        return {"cog_code_retenu": code, "cog_statut": ARRONDISSEMENT,
                "cog_successeurs": "",
                "cog_libelle": index["libelles"].get(rattachement, "")}

    successeurs = index["successeurs"].get(code)
    if successeurs:
        if len(successeurs) == 1:
            retenu = successeurs[0]
            return {"cog_code_retenu": retenu, "cog_statut": CORRIGE,
                    "cog_successeurs": retenu,
                    "cog_libelle": index["libelles"].get(retenu, "")}
        # scission sans survie du code d'origine : on conserve et on signale
        return {"cog_code_retenu": code, "cog_statut": AMBIGU,
                "cog_successeurs": "|".join(successeurs), "cog_libelle": ""}

    if code[:2] in PREFIXES_HORS_COG:
        return {"cog_code_retenu": code, "cog_statut": HORS_COG,
                "cog_successeurs": "", "cog_libelle": ""}

    return {"cog_code_retenu": code, "cog_statut": INCONNU,
            "cog_successeurs": "", "cog_libelle": ""}


def valider(df: pd.DataFrame, col_source: str, index: dict) -> pd.DataFrame:
    """Ajoute les colonnes de validation COG à une table de structures.

    `col_source` est la colonne brute du code commune — `TX_CogCommune` — et non
    sa version normalisée par le pipeline, qui a déjà perdu les lettres corses.
    """
    df = df.copy()
    codes = df[col_source].map(normaliser_code_commune)

    distincts = {c: resoudre(c, index) for c in codes.unique()}
    resolution = pd.DataFrame([distincts[c] for c in codes], index=df.index)

    df["cog_code_origine"] = codes
    for colonne in ("cog_code_retenu", "cog_statut", "cog_successeurs", "cog_libelle"):
        df[colonne] = resolution[colonne]

    df["cog_anomalie"] = df["cog_statut"].isin([AMBIGU, INCONNU, ABSENT])
    return df


def reparer_corse(df: pd.DataFrame, col_normalisee: str) -> pd.Series:
    """Repère les codes corses abîmés par la normalisation du pipeline.

    `pretraiter_code_commune` supprime tout caractère non numérique : `2A004`
    devient `02004`, soit un code de l'Aisne, et la structure est routée dans le
    mauvais département. Renvoie un booléen par ligne.
    """
    origine = df["cog_code_origine"].fillna("").astype(str)
    normalisee = df[col_normalisee].fillna("").astype(str)
    return origine.str[:2].isin(["2A", "2B"]) & (origine != normalisee)


def appliquer(df: pd.DataFrame, col_commune_norm: str, col_dept: str) -> pd.DataFrame:
    """Réécrit le code commune normalisé et le département à partir du COG.

    Les phases suivantes lisent ces deux colonnes : c'est le seul point par
    lequel la validation influence le matching.
    """
    df = df.copy()
    df[col_commune_norm] = df["cog_code_retenu"]
    df[col_dept] = df["cog_code_retenu"].map(extraire_departement).replace("", "INCONNU")
    return df


def rapport(df: pd.DataFrame, libelle: str = "structures") -> pd.DataFrame:
    """Répartition par statut, avec le détail de ce qui a effectivement changé."""
    compte = df["cog_statut"].value_counts()
    total = len(df)

    lignes = [{"Statut": s, "Nombre": int(compte.get(s, 0)),
               "Part": f"{compte.get(s, 0) / total * 100:.2f} %"}
              for s in STATUTS if compte.get(s, 0) > 0]
    lignes.append({"Statut": "TOTAL", "Nombre": total, "Part": "100 %"})

    modifies = int((df["cog_code_origine"] != df["cog_code_retenu"]).sum())
    dept_change = int((df["cog_code_origine"].str[:2] != df["cog_code_retenu"].str[:2]).sum())

    print(f"Validation COG sur {total:,} {libelle}")
    print(f"   codes modifiés            : {modifies:,}")
    print(f"   dont changement de dept.  : {dept_change:,}")
    print(f"   anomalies signalées       : {int(df['cog_anomalie'].sum()):,}")
    return pd.DataFrame(lignes)

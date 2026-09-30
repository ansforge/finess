"""Routage des signalements email et téléphone vers l'autorité d'enregistrement.

Traitement indépendant des chantiers email et téléphone : il relit les classeurs
Excel déjà exportés par ces chantiers et ne modifie ni ne redéclenche rien en
amont. La catégorie d'établissement, absente des exports, est récupérée ici par
une requête directe sur FINESS+.

Réutilise src/autorites.py — référentiel des catégories, résolution
catégorie + département vers autorité — tel quel.

Deux règles reprises du classement par AE de la sirenisation. Une personne
morale rattachée à un seul établissement hérite du résultat de celui-ci ; avec
plusieurs, la famille d'autorité majoritaire parmi les domaines des catégories
des fils l'emporte, à condition d'être strictement majoritaire.
"""
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import autorites as aut

COULEUR_HEADER = "1F3864"

CLE_EGE = "NB_EgeId"
CLE_PM = "NB_PmSmsseId"
COL_CATEGORIE = "TX_CategorieEntiteGeographiqueExercice"

SOURCE_CATEGORIE = "CATEGORIE"
SOURCE_EGE_UNIQUE = "EGE_UNIQUE"
SOURCE_MAJORITE = "MAJORITE_DOMAINE"


def router_ege(df: pd.DataFrame, categories_ege: pd.DataFrame,
               referentiel: pd.DataFrame) -> pd.DataFrame:
    """Route un lot de signalements EGE.

    La catégorie est portée par la structure elle-même : jointure directe sur
    l'identifiant métier.
    """
    df = df.copy()
    df[CLE_EGE] = df[CLE_EGE].astype("string").str.strip()

    lookup = (categories_ege.assign(**{CLE_EGE: categories_ege[CLE_EGE].astype("string").str.strip()})
              .drop_duplicates(CLE_EGE).set_index(CLE_EGE))
    df[COL_CATEGORIE] = df[CLE_EGE].map(lookup[COL_CATEGORIE])
    if "TX_CogCommune" not in df.columns:
        df["TX_CogCommune"] = df[CLE_EGE].map(lookup["TX_CogCommune"])

    df["departement"] = df["TX_CogCommune"].map(aut.extraire_departement)
    resultat = aut.affecter(df, referentiel, COL_CATEGORIE, "departement")
    resultat["origine_categorie"] = "STRUCTURE"
    resultat["autorite_source"] = resultat["autorite_statut"].map(
        lambda s: SOURCE_CATEGORIE if s == aut.RESOLU else "")
    return resultat


def router_pm(df: pd.DataFrame, categories_ege: pd.DataFrame,
              referentiel: pd.DataFrame) -> pd.DataFrame:
    """Route un lot de signalements PM depuis leurs établissements.

    Le département retenu reste celui de la personne morale : c'est elle qui est
    envoyée au gestionnaire, la commune des établissements ne sert qu'à résoudre
    leur propre autorité.
    """
    df = df.copy()
    df[CLE_PM] = df[CLE_PM].astype("string").str.strip()
    df["departement"] = df["TX_CogCommune"].map(aut.extraire_departement)

    ege = categories_ege.copy()
    ege[CLE_PM] = ege[CLE_PM].astype("string").str.strip()
    ege["departement"] = ege["TX_CogCommune"].map(aut.extraire_departement)
    ege = aut.affecter(ege, referentiel, COL_CATEGORIE, "departement")

    categorie = (ege[COL_CATEGORIE].fillna("").astype(str).str.strip().str.zfill(3))
    ege["famille_categorie"] = categorie.map(referentiel["famille"]).fillna("")

    depts_pm = df.drop_duplicates(CLE_PM).set_index(CLE_PM)["departement"]
    consolide = _consolider_pm(ege, depts_pm)

    for colonne in [*aut.COLONNES_ROUTAGE, "autorite_source", "origine_categorie",
                    "nb_ege_fils", "familles_fils"]:
        df[colonne] = df[CLE_PM].map(consolide[colonne]) if colonne in consolide else pd.NA

    orphelines = df["autorite_statut"].isna()
    df.loc[orphelines, "autorite_statut"] = aut.NON_DETERMINEE
    df.loc[orphelines, "autorite_motif"] = "aucun_ege_rattache"
    df.loc[orphelines, "origine_categorie"] = "AUCUNE"
    for colonne in ["autorite_code", "autorite_candidats", "autorite_source", "familles_fils"]:
        df[colonne] = df[colonne].fillna("")
    df["nb_ege_fils"] = df["nb_ege_fils"].fillna(0).astype(int)
    df[COL_CATEGORIE] = df.get(COL_CATEGORIE, pd.NA)
    return df


def _consolider_pm(ege: pd.DataFrame, depts_pm: pd.Series) -> pd.DataFrame:
    """Autorité de chaque personne morale à partir de ses établissements."""
    lignes = []

    for pm_id, groupe in ege.groupby(CLE_PM, dropna=True):
        pm_id = str(pm_id).strip()
        nb = len(groupe)

        if nb == 1:
            fils = groupe.iloc[0]
            lignes.append({
                CLE_PM: pm_id,
                "autorite_statut": fils["autorite_statut"],
                "autorite_code": fils["autorite_code"],
                "autorite_candidats": fils["autorite_candidats"],
                "autorite_motif": fils["autorite_motif"],
                "autorite_source": SOURCE_EGE_UNIQUE,
                "origine_categorie": "EGE_UNIQUE",
                "nb_ege_fils": 1,
                "familles_fils": fils["famille_categorie"],
            })
            continue

        famille, votes, votants = aut.majorite_famille(groupe["famille_categorie"])
        detail = "|".join(f"{f}:{n}" for f, n in
                          groupe["famille_categorie"].replace("", pd.NA).dropna()
                          .value_counts().items())
        region = aut.DEPT_REGION.get(str(depts_pm.get(pm_id, "")).strip(), "")

        if famille and region:
            lignes.append({
                CLE_PM: pm_id,
                "autorite_statut": aut.RESOLU,
                "autorite_code": aut.code_famille(famille, region),
                "autorite_candidats": "", "autorite_motif": "",
                "autorite_source": SOURCE_MAJORITE,
                "origine_categorie": "EGE_FILS",
                "nb_ege_fils": nb, "familles_fils": detail,
            })
            continue

        if famille and not region:
            statut, motif = aut.NON_DETERMINEE, "departement_pm_hors_perimetre"
        elif votants == 0:
            statut, motif = aut.NON_DETERMINEE, "aucun_ege_exploitable"
        else:
            statut, motif = aut.A_ARBITRER, "domaine_fils_partage"

        candidats = ""
        if statut == aut.A_ARBITRER and region:
            candidats = "|".join(sorted(
                {aut.code_famille(f, region) for f in groupe["famille_categorie"] if f}))

        lignes.append({
            CLE_PM: pm_id,
            "autorite_statut": statut, "autorite_code": "",
            "autorite_candidats": candidats, "autorite_motif": motif,
            "autorite_source": "", "origine_categorie": "EGE_FILS",
            "nb_ege_fils": nb, "familles_fils": detail,
        })

    colonnes = [CLE_PM, *aut.COLONNES_ROUTAGE, "autorite_source",
                "origine_categorie", "nb_ege_fils", "familles_fils"]
    return pd.DataFrame(lignes, columns=colonnes).set_index(CLE_PM)


def enrichir_libelles(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    code = df["autorite_code"].fillna("")
    df["type_autorite"] = code.str.split("-").str[0]
    df["region"] = code.str.split("-").str[1].fillna("")
    df["libelle_region"] = df["region"].map(aut.LIBELLES_REGION).fillna("")
    return df


def combiner(res_ege: pd.DataFrame, res_pm: pd.DataFrame) -> pd.DataFrame:
    """Combine les résultats EGE et PM d'un même groupe, avec une colonne
    type_structure ('EGE' / 'PM'), pour produire un classeur unique par autorité."""
    ege = res_ege.copy()
    ege.insert(0, "type_structure", "EGE")
    ege["cle_structure"] = "EGE-" + ege[CLE_EGE].astype(str)
    pm = res_pm.copy()
    pm.insert(0, "type_structure", "PM")
    pm["cle_structure"] = "PM-" + pm[CLE_PM].astype(str)
    return pd.concat([ege, pm], ignore_index=True, sort=False)


def _ascii(texte: str) -> str:
    plat = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", plat).strip("-")


def _nom_fichier(groupe: str, prefixe: str, region: str) -> str:
    suffixe = f"_{_ascii(region)}" if region else ""
    return f"{prefixe}_{groupe}{suffixe}.xlsx"


def _mettre_en_forme(ws, nb_lignes: int) -> None:
    entete = PatternFill("solid", fgColor=COULEUR_HEADER)
    bordure = Border(*[Side(style="thin", color="D9D9D9")] * 4)
    for cellule in ws[1]:
        cellule.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
        cellule.fill = entete
        cellule.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cellule.border = bordure
    for ligne in ws.iter_rows(min_row=2, max_row=nb_lignes + 1):
        for cellule in ligne:
            cellule.font = Font(name="Arial", size=9)
            cellule.border = bordure
    for idx, colonne in enumerate(ws.iter_cols(min_row=1, max_row=min(nb_lignes + 1, 200)), start=1):
        largeur = max((len(str(c.value)) for c in colonne if c.value is not None), default=8)
        ws.column_dimensions[get_column_letter(idx)].width = min(max(largeur + 2, 10), 45)
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def _synthese(df: pd.DataFrame, cle: str, colonne_repartition: str = None) -> pd.DataFrame:
    if colonne_repartition and colonne_repartition in df.columns:
        synthese = (df.groupby(["departement", colonne_repartition])[cle]
                    .nunique().unstack(fill_value=0).reset_index())
        valeurs = sorted(df[colonne_repartition].dropna().unique().tolist())
        for v in valeurs:
            if v not in synthese.columns:
                synthese[v] = 0
        synthese = synthese[["departement", *valeurs]].sort_values("departement")
        synthese["TOTAL"] = synthese[valeurs].sum(axis=1)
        synthese.loc[len(synthese)] = ["TOTAL", *synthese[valeurs].sum(), synthese["TOTAL"].sum()]
        return synthese

    synthese = (df.groupby("departement")[cle].nunique()
                .reset_index(name="Nombre").sort_values("departement"))
    synthese.loc[len(synthese)] = ["TOTAL", synthese["Nombre"].sum()]
    return synthese


def colonnes_disponibles(*dfs: pd.DataFrame) -> list:
    """Colonnes exportables. Avec plusieurs DataFrame, ne retourne que celles présentes
    dans tous, pour composer une liste utilisable sur chacun d'eux."""
    listes = [[c for c in df.columns if c != "_groupe"] for df in dfs]
    communes = set.intersection(*(set(l) for l in listes)) if listes else set()
    return [c for c in listes[0] if c in communes] if listes else []


def exporter(df: pd.DataFrame, dossier, prefixe: str, cle: str = "cle_structure",
             nom_feuille: str = "Structures", colonne_repartition: str = None,
             colonnes=None, nettoyer: bool = True) -> pd.DataFrame:
    """Écrit un classeur par autorité (+ A_ARBITRER + NON_DETERMINEE), une feuille
    de synthèse par département (ventilée par colonne_repartition si fournie) et
    une feuille de données.

    colonnes restreint la feuille de données aux colonnes demandées, dans l'ordre donné ;
    None les conserve toutes. Les colonnes de tri, de regroupement et de synthèse restent
    utilisées en interne même si elles ne figurent pas dans la liste.
    """
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)

    if colonnes is not None:
        inconnues = [c for c in colonnes if c not in df.columns]
        if inconnues:
            raise ValueError(f"Colonnes inconnues : {inconnues}\n"
                             f"Disponibles : {colonnes_disponibles(df)}")

    if nettoyer:
        for ancien in dossier.glob(f"{prefixe}_*.xlsx"):
            ancien.unlink()

    df = df.copy()
    df["_groupe"] = df["autorite_code"].where(df["autorite_statut"] == aut.RESOLU,
                                              df["autorite_statut"])

    recap = []
    for groupe, bloc in df.groupby("_groupe", dropna=False):
        bloc = bloc.drop(columns="_groupe").sort_values(["departement", cle])
        region = bloc["libelle_region"].iloc[0] if "libelle_region" in bloc.columns else ""
        chemin = dossier / _nom_fichier(str(groupe), prefixe, region)

        synthese = _synthese(bloc, cle, colonne_repartition)
        donnees = bloc[list(colonnes)] if colonnes is not None else bloc

        with pd.ExcelWriter(chemin, engine="openpyxl") as writer:
            synthese.to_excel(writer, sheet_name="Synthèse", index=False)
            _mettre_en_forme(writer.sheets["Synthèse"], len(synthese))
            donnees.to_excel(writer, sheet_name=nom_feuille, index=False)
            _mettre_en_forme(writer.sheets[nom_feuille], len(donnees))

        recap.append({"autorite": groupe, "region": region, "fichier": chemin.name,
                      "nb_structures": bloc[cle].nunique(),
                      "nb_departements": bloc["departement"].nunique()})

    return (pd.DataFrame(recap).sort_values("nb_structures", ascending=False)
            .reset_index(drop=True))

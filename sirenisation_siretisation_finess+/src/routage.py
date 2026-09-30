"""Routage des structures non résolues en phase 3 vers leur autorité
d'enregistrement, et export d'un classeur Excel par autorité."""
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import DB_SCHEMA
from src import autorites as aut

STATUTS_CIBLES = ["DOUTEUX", "REJETE", "NON_FIABLE_APE"]
NOMS_FEUILLES = {"DOUTEUX": "Douteux", "REJETE": "Rejeté",
                 "NON_FIABLE_APE": "Non_fiable_APE"}

CLE_PM = "TX_NumFinessPm"
CLE_EGE = "TX_NumFinessEge"

COLONNES_EGE_FILS = ["NB_EgeId", "NB_PmSmsseId", "TX_NumFinessEge",
                     "TX_CategorieEntiteGeographiqueExercice", "TX_CogCommune",
                     "FK_MetadonneeId"]

COLONNES_CONTACT = ["TEL_MAIL", "TEL_TELEPHONE", "TEL_TELECOPIE"]

COLONNES_TETE = [
    "autorite_code", "type_autorite", "libelle_autorite", "region", "libelle_region",
    "departement", "autorite_statut", "autorite_source", "autorite_candidats",
    "autorite_motif", "ae_declaree_finess",
    "libelle_categorie", "domaine_categorie", "origine_categorie",
]

SOURCE_CATEGORIE = "CATEGORIE"
SOURCE_FINESS = "FINESS_PLUS"
SOURCE_EGE_UNIQUE = "EGE_UNIQUE"
SOURCE_MAJORITE = "MAJORITE_DOMAINE"

LIBELLES_AUTORITE = {
    "ARS": "Agence régionale de santé",
    "DREETS": "Direction régionale de l'économie, de l'emploi, du travail et des solidarités",
    "DEETS": "Direction de l'économie, de l'emploi, du travail et des solidarités",
    "DRHIL": "Direction régionale et interdépartementale de l'hébergement et du logement",
    "AT": "Agence territoriale de santé",
    "ANS": "Agence du numérique en santé",
}

COULEURS_HEADER = {"DOUTEUX": "D4A017", "REJETE": "C0392B",
                   "NON_FIABLE_APE": "8E44AD", "Synthèse": "1F3864"}
COULEURS_LIGNES = {"DOUTEUX": "FFF8E7", "REJETE": "FDEDEC",
                   "NON_FIABLE_APE": "F4ECF7"}


# Le nom de la colonne de commune varie selon la source : les tables chargées
# portent TX_CogCommune, les exports de phase le nom normalisé du prétraitement.
COLONNES_COMMUNE = ["TX_CogCommune", "cdcommune_norm_pm", "cdcommune_norm_ege"]


def _colonne_commune(df: pd.DataFrame, contexte: str = "") -> str:
    for colonne in COLONNES_COMMUNE:
        if colonne in df.columns:
            return colonne
    raise KeyError(
        f"Aucune colonne de commune dans {contexte or 'le DataFrame'} : "
        f"attendu l'une de {COLONNES_COMMUNE}, trouve {list(df.columns)[:15]}")


# ─── Chargement ──────────────────────────────────────────────────────────────

def charger_phase3(chemin, col_cle: str, feuille: str = "Top3",
                   col_statut: str = "statut_candidat",
                   col_rang: str = "rang") -> pd.DataFrame:
    """Structures non resolues en phase 3, avec leur top 3 complet.

    Cote siretisation, passer col_statut="statut_structure" : le verdict tient
    compte du controle d'activite, qui peut bloquer une structure que le score
    validait.
    """
    """Charge la phase 3 et ne garde que les structures dont le rang 1 est
    DOUTEUX ou REJETE, avec l'intégralité de leur top 3."""
    df = pd.read_excel(chemin, sheet_name=feuille, dtype=str)
    df[col_rang] = pd.to_numeric(df[col_rang], errors="coerce")

    rang1 = df[df[col_rang] == 1]
    cibles = rang1[rang1[col_statut].isin(STATUTS_CIBLES)]

    df = df[df[col_cle].isin(set(cibles[col_cle]))].copy()
    df["statut_structure"] = df[col_cle].map(rang1.set_index(col_cle)[col_statut])

    return df.sort_values([col_cle, col_rang]).reset_index(drop=True)


def charger_ae_declaree(conn, tables: dict) -> pd.DataFrame:
    """Autorité déclarée dans FINESS+, par identifiant de métadonnée.

    La table Metadonnee porte plus de 5 millions de lignes tous objets
    confondus. La correspondance n'est construite que sur les métadonnées
    référencées par une personne morale ou un établissement, ce qui la ramène à
    l'ordre de quelques centaines de milliers de lignes.
    """
    requete = f"""
        SELECT m.NB_MetadonneeId, g.TX_AutoriteEnregistrement, g.TX_Gest
        FROM [{DB_SCHEMA}].[{tables['metadonnee']}] m
        JOIN [{DB_SCHEMA}].[{tables['gestionnaire']}] g
          ON g.NB_GestionnaireId = m.NB_GestionnaireId
        WHERE EXISTS (SELECT 1 FROM [{DB_SCHEMA}].[{tables['pm']}] p
                      WHERE p.FK_MetadonneeId = m.NB_MetadonneeId
                        AND p.BL_VersionCourante = 1)
           OR EXISTS (SELECT 1 FROM [{DB_SCHEMA}].[{tables['ege']}] e
                      WHERE e.FK_MetadonneeId = m.NB_MetadonneeId
                        AND e.BL_VersionCourante = 1)
    """
    df = pd.read_sql(requete, conn)
    df["ae_declaree_finess"] = df["TX_AutoriteEnregistrement"].map(aut.normaliser_autorite)
    df["NB_MetadonneeId"] = df["NB_MetadonneeId"].astype(str).str.strip()

    renseignees = int((df["ae_declaree_finess"] != "").sum())
    print(f"   {len(df):,} metadonnees rattachees a un gestionnaire, "
          f"{renseignees:,} avec une autorite exploitable")
    return df[["NB_MetadonneeId", "ae_declaree_finess", "TX_Gest"]]


def charger_ege_fils(chemin_parquet, pm_ids) -> pd.DataFrame:
    """Établissements rattachés aux personnes morales données.

    Le rattachement passe par NB_PmSmsseId, un identifiant entier, là où
    l'ancien modèle comparait des numéros FINESS sous forme de chaînes.
    """
    cibles = {str(i).strip() for i in pm_ids if i and not pd.isna(i)}

    ege = pd.read_parquet(chemin_parquet, columns=COLONNES_EGE_FILS)
    ege["NB_PmSmsseId"] = ege["NB_PmSmsseId"].astype("string").str.strip()
    ege = ege[ege["NB_PmSmsseId"].isin(cibles)]

    return ege.reset_index(drop=True)


def joindre_contacts(df: pd.DataFrame, contacts: pd.DataFrame,
                     col_cle: str) -> pd.DataFrame:
    """Ajoute les coordonnées à une table de structures."""
    if contacts.empty:
        for colonne in COLONNES_CONTACT:
            df[colonne] = pd.NA
        return df

    contacts = contacts.copy()
    contacts[col_cle] = contacts[col_cle].astype(str).str.strip()

    df = df.copy()
    df[col_cle] = df[col_cle].astype(str).str.strip()
    df = df.merge(contacts, on=col_cle, how="left")

    for colonne in COLONNES_CONTACT:
        if colonne in df.columns:
            print(f"   {colonne:<16} {int(df[colonne].notna().sum()):,} renseignes")
    return df


# ─── Rattrapage par l'autorité déclarée ──────────────────────────────────────

def rattraper_ae_declaree(df: pd.DataFrame, ae_par_meta: pd.DataFrame,
                          col_meta: str = "FK_MetadonneeId") -> pd.DataFrame:
    """Reprend les structures non résolues avec l'autorité déclarée dans FINESS+.

    N'intervient que sur A_ARBITRER et NON_DETERMINEE. Une autorité déclarée,
    territoriale ou ANS, rend la structure résolue ; sinon le classement issu de
    la catégorie est conservé tel quel.
    """
    df = df.copy()
    if col_meta not in df.columns:
        print(f"   {col_meta} absente, rattrapage ignore")
        df["ae_declaree_finess"] = ""
        return df

    correspondance = ae_par_meta.set_index("NB_MetadonneeId")["ae_declaree_finess"]
    df["ae_declaree_finess"] = (df[col_meta].astype(str).str.strip()
                                .map(correspondance).fillna(""))

    a_reprendre = (df["autorite_statut"] != aut.RESOLU) & (df["ae_declaree_finess"] != "")
    df.loc[a_reprendre, "autorite_code"] = df.loc[a_reprendre, "ae_declaree_finess"]
    df.loc[a_reprendre, "autorite_statut"] = aut.RESOLU
    df.loc[a_reprendre, "autorite_source"] = SOURCE_FINESS
    df.loc[a_reprendre, "autorite_candidats"] = ""
    df.loc[a_reprendre, "autorite_motif"] = ""

    print(f"   {int(a_reprendre.sum()):,} structures resolues par l'autorite declaree")
    return df


# ─── Routage siretisation ────────────────────────────────────────────────────

def router_siretisation(df: pd.DataFrame, referentiel: pd.DataFrame,
                        ae_par_meta: pd.DataFrame) -> pd.DataFrame:
    """Route des EGE, dont la catégorie est portée par la structure elle-même."""
    df = df.copy()
    df["departement"] = df[_colonne_commune(df, "les EGE a router")].map(
        aut.extraire_departement)
    df = aut.affecter(df, referentiel, "TX_CategorieEntiteGeographiqueExercice", "departement")
    df["origine_categorie"] = "STRUCTURE"
    df["autorite_source"] = df["autorite_statut"].map(
        lambda s: SOURCE_CATEGORIE if s == aut.RESOLU else "")

    df = rattraper_ae_declaree(df, ae_par_meta)
    return _enrichir(df, referentiel)


# ─── Routage sirenisation ────────────────────────────────────────────────────

def router_sirenisation(df: pd.DataFrame, referentiel: pd.DataFrame,
                        df_ege_fils: pd.DataFrame,
                        ae_par_meta: pd.DataFrame) -> pd.DataFrame:
    """Route des personnes morales à partir de leurs établissements.

    Une PM avec un seul EGE hérite intégralement du résultat de celui-ci. Avec
    plusieurs, on cherche la famille d'autorité majoritaire parmi les domaines
    des catégories de ses fils : Sanitaire et Médico-social votent ARS, Social
    et Formation votent solidarités. La majorité doit être stricte.

    Le département retenu reste celui de la PM : c'est elle qui est envoyée au
    gestionnaire, la commune des EGE ne sert qu'à résoudre leur propre autorité.
    """
    df = df.copy()
    df["departement"] = df[_colonne_commune(df, "les PM a router")].map(
        aut.extraire_departement)

    ege = df_ege_fils.copy()
    ege["departement"] = ege[_colonne_commune(ege, "les EGE fils")].map(
        aut.extraire_departement)
    ege = aut.affecter(ege, referentiel, "TX_CategorieEntiteGeographiqueExercice", "departement")
    ege["autorite_source"] = ege["autorite_statut"].map(
        lambda s: SOURCE_CATEGORIE if s == aut.RESOLU else "")
    ege = rattraper_ae_declaree(ege, ae_par_meta)

    categorie_ege = (ege["TX_CategorieEntiteGeographiqueExercice"]
                     .fillna("").astype(str).str.strip().str.zfill(3))
    ege["famille_categorie"] = categorie_ege.map(referentiel["famille"]).fillna("")

    consolide = _consolider_pm(ege, referentiel, df.set_index("NB_PmSmsseId")["departement"]
                               if "NB_PmSmsseId" in df.columns else pd.Series(dtype=str))

    for colonne in [*aut.COLONNES_ROUTAGE, "autorite_source", "origine_categorie",
                    "nb_ege_fils", "familles_fils"]:
        df[colonne] = df["NB_PmSmsseId"].astype(str).str.strip().map(
            consolide[colonne] if colonne in consolide else pd.Series(dtype=object))

    orphelines = df["autorite_statut"].isna()
    df.loc[orphelines, "autorite_statut"] = aut.NON_DETERMINEE
    df.loc[orphelines, "autorite_motif"] = "aucun_ege_rattache"
    df.loc[orphelines, "origine_categorie"] = "AUCUNE"
    for colonne in ["autorite_code", "autorite_candidats", "autorite_source", "familles_fils"]:
        df[colonne] = df[colonne].fillna("")
    df["nb_ege_fils"] = df["nb_ege_fils"].fillna(0).astype(int)

    df = rattraper_ae_declaree(df, ae_par_meta)
    return _enrichir(df, referentiel)


def _consolider_pm(ege: pd.DataFrame, referentiel: pd.DataFrame,
                   depts_pm: pd.Series) -> pd.DataFrame:
    """Autorité de chaque PM à partir de ses établissements déjà routés."""
    lignes = []

    for pm_id, groupe in ege.groupby("NB_PmSmsseId", dropna=True):
        pm_id = str(pm_id).strip()
        nb = len(groupe)

        if nb == 1:
            fils = groupe.iloc[0]
            lignes.append({
                "NB_PmSmsseId": pm_id,
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
            code = aut.code_famille(famille, region)
            lignes.append({
                "NB_PmSmsseId": pm_id,
                "autorite_statut": aut.RESOLU, "autorite_code": code,
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
                {aut.code_famille(f, region)
                 for f in groupe["famille_categorie"] if f}))

        lignes.append({
            "NB_PmSmsseId": pm_id,
            "autorite_statut": statut, "autorite_code": "",
            "autorite_candidats": candidats, "autorite_motif": motif,
            "autorite_source": "", "origine_categorie": "EGE_FILS",
            "nb_ege_fils": nb, "familles_fils": detail,
        })

    colonnes = ["NB_PmSmsseId", *aut.COLONNES_ROUTAGE, "autorite_source",
                "origine_categorie", "nb_ege_fils", "familles_fils"]
    return pd.DataFrame(lignes, columns=colonnes).set_index("NB_PmSmsseId")


# ─── Enrichissement et export ────────────────────────────────────────────────

def _enrichir(df: pd.DataFrame, referentiel: pd.DataFrame) -> pd.DataFrame:
    col_categorie = "TX_CategorieEntiteGeographiqueExercice"
    if col_categorie in df.columns:
        categorie = (df[col_categorie].where(df[col_categorie].notna(), "")
                     .astype(str).str.strip().str.zfill(3))
        df["libelle_categorie"] = categorie.map(referentiel["libelle_court"]).fillna("")
        df["domaine_categorie"] = categorie.map(referentiel["domaine"]).fillna("")
    else:
        df["libelle_categorie"] = ""
        df["domaine_categorie"] = ""

    code = df["autorite_code"].fillna("")
    df["type_autorite"] = code.str.split("-").str[0]
    df["region"] = code.str.split("-").str[1].fillna("")
    df["libelle_region"] = df["region"].map(aut.LIBELLES_REGION).fillna("")
    df["libelle_autorite"] = df["type_autorite"].map(LIBELLES_AUTORITE).fillna("")

    for colonne in COLONNES_TETE:
        if colonne not in df.columns:
            df[colonne] = ""

    reste = [c for c in df.columns if c not in COLONNES_TETE]
    return df[COLONNES_TETE + reste]


def colonnes_disponibles(df: pd.DataFrame) -> list:
    """Liste des colonnes exportables, dans leur ordre d'apparition."""
    return [c for c in df.columns if c != "_groupe"]


def exporter(df: pd.DataFrame, dossier, prefixe: str, col_cle: str,
             col_rang: str = "rang", colonnes=None, nettoyer: bool = True) -> pd.DataFrame:
    """Écrit un classeur par autorité, plus un classeur A_ARBITRER et un NON_DETERMINEE.

    colonnes restreint les feuilles de données aux colonnes demandées, dans l'ordre donné ;
    None les conserve toutes. Les colonnes de tri et de découpage restent utilisées en
    interne même si elles ne figurent pas dans la liste.

    Les classeurs du même préfixe issus d'une exécution précédente sont supprimés au
    préalable : le découpage dépend du contenu des données, un fichier obsolète resterait
    sinon en place sans être écrasé.
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
        bloc = bloc.drop(columns="_groupe").sort_values(
            ["departement", col_cle, col_rang])
        region = bloc["libelle_region"].iloc[0]
        chemin = dossier / _nom_fichier(str(groupe), prefixe, region)

        recap.append({"autorite": groupe, "region": region, "fichier": chemin.name,
                      "nb_structures": _ecrire_classeur(bloc, chemin, col_cle,
                                                        col_rang, colonnes),
                      "nb_lignes": len(bloc),
                      "nb_departements": bloc["departement"].nunique()})

    return (pd.DataFrame(recap)
            .sort_values("nb_structures", ascending=False)
            .reset_index(drop=True))


def _nom_fichier(groupe: str, prefixe: str, region: str) -> str:
    suffixe = f"_{_ascii(region)}" if region else ""
    return f"{prefixe}_{groupe}{suffixe}.xlsx"


def _ascii(texte: str) -> str:
    plat = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", plat).strip("-")


def _ecrire_classeur(bloc: pd.DataFrame, chemin: Path, col_cle: str,
                     col_rang: str, colonnes=None) -> int:
    rang1 = bloc[pd.to_numeric(bloc[col_rang], errors="coerce") == 1]
    synthese = _synthese(rang1, col_cle)

    with pd.ExcelWriter(chemin, engine="openpyxl") as writer:
        synthese.to_excel(writer, sheet_name="Synthèse", index=False)
        _mettre_en_forme(writer.sheets["Synthèse"], "Synthèse", len(synthese))

        for statut in STATUTS_CIBLES:
            feuille = bloc[bloc["statut_structure"] == statut]
            if feuille.empty:
                continue
            if colonnes is not None:
                feuille = feuille[list(colonnes)]
            nom = NOMS_FEUILLES[statut]
            feuille.to_excel(writer, sheet_name=nom, index=False)
            _mettre_en_forme(writer.sheets[nom], statut, len(feuille))

    return rang1[col_cle].nunique()


def _synthese(rang1: pd.DataFrame, col_cle: str) -> pd.DataFrame:
    synthese = (rang1.groupby(["departement", "statut_structure"])[col_cle]
                .nunique().unstack(fill_value=0).reset_index())

    for statut in STATUTS_CIBLES:
        if statut not in synthese.columns:
            synthese[statut] = 0

    synthese = synthese[["departement", *STATUTS_CIBLES]].sort_values("departement")
    synthese["TOTAL"] = synthese[STATUTS_CIBLES].sum(axis=1)
    synthese.loc[len(synthese)] = ["TOTAL", *synthese[STATUTS_CIBLES].sum(),
                                   synthese["TOTAL"].sum()]

    return synthese


def _mettre_en_forme(ws, cle_couleur: str, nb_lignes: int) -> None:
    entete = PatternFill("solid", fgColor=COULEURS_HEADER.get(cle_couleur, "1F3864"))
    remplissage = COULEURS_LIGNES.get(cle_couleur)
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
            if remplissage:
                cellule.fill = PatternFill("solid", fgColor=remplissage)

    for idx, colonne in enumerate(ws.iter_cols(min_row=1, max_row=min(nb_lignes + 1, 200)), start=1):
        largeur = max((len(str(c.value)) for c in colonne if c.value is not None), default=8)
        ws.column_dimensions[get_column_letter(idx)].width = min(max(largeur + 2, 10), 45)

    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

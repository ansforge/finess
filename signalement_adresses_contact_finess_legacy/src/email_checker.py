"""Contrôle qualité des adresses email FINESS (EG/EJ).

Pour chaque email : un niveau + code d'anomalie, une classification de la partie
locale, une correspondance avec la raison sociale/adresse, et une détection
géographique. Niveaux : 0 valide, 1 critique (inutilisable), 2 à surveiller.
"""

import re
import unicodedata
from pathlib import Path

import pandas as pd


DOMAINES_PERSONNELS = {
    "gmail.com", "googlemail.com",
    "outlook.com", "outlook.fr", "hotmail.com", "hotmail.fr",
    "live.com", "live.fr", "msn.com",
    "yahoo.com", "yahoo.fr", "ymail.com",
    "icloud.com", "me.com", "mac.com",
    "orange.fr", "wanadoo.fr", "free.fr", "sfr.fr", "sfr.net",
    "bbox.fr", "neuf.fr", "club-internet.fr", "aliceadsl.fr",
    "laposte.net", "numericable.fr",
    "bluewin.ch",
    "proton.me", "protonmail.com", "protonmail.ch",
    "tutanota.com", "tuta.io",
    "mailfence.com",
}

DOMAINES_INEXISTANTS = {
    "gmail.fr", "gmail.net", "gmail.org",
    "googlemail.fr", "googlemail.net",
}

TYPOS_EXTENSIONS = {
    "frr":  ".fr", "ftr":  ".fr", "frl":  ".fr", "fre":  ".fr", "frf":  ".fr",
    "orgt": ".org", "og":   ".org", "prg":  ".org", "orq":  ".org",
    "ccom": ".com", "come": ".com", "cmo":  ".com", "ocm":  ".com",
    "ner":  ".net",
}

EXTENSIONS_FICHIERS = {
    "vcf", "pdf", "doc", "docx", "xlsx", "xls",
    "jpg", "jpeg", "png", "gif",
}

EXTENSIONS_LIEUX = {
    "frkingersheim", "thionville", "strasbourg", "bordeaux",
    "toulouse", "marseille", "lyon", "nantes", "rennes",
    "montpellier", "lille", "nice",
}

PLACEHOLDERS = {
    "aucun", "rien", "na", "n/a", "null", "none",
    "-", ".", "?", "xxx", "0", "non", "vide", "neant",
}

_RE_INTERDITS = re.compile(r'[,;"\'\\\(\)\[\]<>]')


MOTS_GENERIQUES = {
    "contact", "info", "infos", "accueil", "administration", "admin",
    "secretariat", "secretaria", "direction", "directeur", "directrice",
    "courrier", "mairie", "reception", "standard", "bureau",
    "noreply", "donotreply", "postmaster", "webmaster",
    "service", "services", "gestion", "compta", "comptabilite",
    "facturation", "commande", "commandes", "achat", "achats",
    "qualite", "communication", "siege", "agence", "antenne",
    "generale", "general", "responsable", "coordination", "coordinateur",
    "assistant", "assistante", "encadrement", "encadrant",
    "administratif", "administrative", "developpement",
}

ABREV_GENERIQUES = {
    "dir", "sec", "adm", "resp", "gen", "dg", "dga", "sg", "rh", "drh",
    "ce", "cse", "secr", "coord", "secdir", "dirg",
}

MOTS_METIER = {
    "pharmacie", "pharma", "ehpad", "clinique", "hopital", "hospital",
    "cabinet", "centre", "centres", "maison", "residence", "residences",
    "foyer", "institut", "laboratoire", "labo", "ssiad", "esat",
    "creche", "sessad", "cmpp", "cattp",
    "association", "asso", "fondation", "mutuelle", "groupe",
    "sante", "medical", "medico", "social", "soins", "infirmier",
    "infirmiere", "selarl", "selas",
    "polyclinique", "dispensaire", "csapa", "caarud", "ccas",
    "etablissement", "structure", "unite", "pole",
    "jeunes", "enfance", "famille", "handicap", "domicile",
    "aide", "secours", "hebergement", "accompagnement",
    "emploi", "passerelle", "tutelle", "curatelle", "logement", "insertion",
    "mandataire", "protection", "majeur", "majeurs", "udaf", "atmp",
    "reinsertion", "reeducation", "readaptation", "formation",
    "apprentissage", "scolaire", "education", "educatif", "pedagogique",
}

SIGLES_METIER = {
    "ccas", "cias", "ifsi", "ifas", "pmi", "savs", "samsah", "camsp",
    "ime", "clic", "rpa", "esat", "sessad", "ssiad", "mas", "fam", "had",
    "itep", "cmp", "cmpp", "cattp", "scp", "scm", "sas", "ssr", "cada",
    "chrs", "saad", "mecs", "cph", "ada", "apa", "mdph", "spasad",
    "ueros", "esms", "ehpa", "marpa", "pasa", "uhr",
}

MOTS_COURTS_METIER = SIGLES_METIER | {"asso", "pole", "labo", "soin"}

MOTS_FONCTION_DIVERS = {
    "cadre", "cadres", "irm", "scanner", "radiologie",
}

MOTS_GEOGRAPHIQUES = {
    "marseille", "marseillane", "paris", "lyon", "toulouse", "nantes",
    "bordeaux", "lille", "nice", "rennes", "strasbourg", "montpellier",
    "salon", "villefranche", "belair", "sever", "gabarn", "brox",
    "nord", "sud", "est", "ouest", "val", "vallee", "vallees",
    "mont", "saint", "sainte", "saintes", "ville", "bourg", "pont",
    "chateau", "roche", "fontaine", "riviere", "bois", "champ", "cote",
    "plaine", "plage", "colline", "coteau", "jumelous", "ecurie", "embellie",
    "grand", "grande", "petit", "petite", "haut", "haute", "bas", "basse",
    "provence", "boulet",
}

MOTS_COURANTS = {
    "mail", "email", "test", "demo", "exemple", "essai",
    "jardin", "jardins", "soleil", "lune", "etoile", "rose", "roses",
    "lieu", "lieux", "vie", "espace", "espaces", "horizon", "avenir",
    "printemps", "ete", "automne", "hiver", "source", "sources",
    "pour", "les", "des", "une", "avec", "sur", "dans",
}

TLDS_VALIDES: set = set()


def charger_tlds_iana(cache: Path) -> set:
    """Charge la liste IANA des TLD (data.iana.org/TLD/tlds-alpha-by-domain.txt)."""
    global TLDS_VALIDES
    cache = Path(cache)
    if not cache.exists():
        raise FileNotFoundError(
            f"Fichier TLD introuvable : {cache}\n"
            f"Télécharge-le depuis https://data.iana.org/TLD/tlds-alpha-by-domain.txt "
            f"et place-le à cet emplacement."
        )
    with open(cache, encoding="utf-8") as f:
        TLDS_VALIDES = {
            line.strip().lower()
            for line in f
            if line.strip() and not line.startswith("#")
        }
    return TLDS_VALIDES


PRENOMS: set = set()
PATRONYMES: set = set()
LONGUEUR_MIN_NOM = 3
LONGUEUR_MIN_SOUSCHAINE = 5

SEUIL_PRENOM = 500
SEUIL_PATRONYME = 100


def _sans_accents(txt: str) -> str:
    nfkd = unicodedata.normalize("NFKD", txt)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normaliser_nom(nom: str) -> str:
    return _sans_accents(str(nom).strip().lower())


def charger_bases_noms(prenoms, patronymes,
                       seuil_prenom: int = SEUIL_PRENOM,
                       seuil_patronyme: int = SEUIL_PATRONYME):
    """Alimente PRENOMS/PATRONYMES à partir des bases data.gouv, filtrées par fréquence.

    prenoms/patronymes : DataFrames (colonne 0 = nom, colonne 1 = fréquence). On ne
    garde que les noms au-dessus du seuil, hors noyau métier/générique/géographique.
    Un iterable simple reste accepté (sans filtrage de fréquence).
    """
    global PRENOMS, PATRONYMES

    def _extraire(source, seuil):
        if isinstance(source, pd.DataFrame):
            col_nom = source.columns[0]
            col_freq = source.columns[1] if source.shape[1] > 1 else None
            if col_freq is not None:
                freq = pd.to_numeric(source[col_freq], errors="coerce").fillna(0)
                source = source[freq >= seuil]
            return set(source[col_nom].astype(str))
        return set(source)

    bruts_prenoms = _extraire(prenoms, seuil_prenom)
    bruts_patronymes = _extraire(patronymes, seuil_patronyme)

    exclus = (MOTS_GEOGRAPHIQUES | MOTS_COURANTS | MOTS_GENERIQUES
              | MOTS_METIER | ABREV_GENERIQUES | SIGLES_METIER
              | MOTS_COURTS_METIER | MOTS_FONCTION_DIVERS)

    PRENOMS = {
        normaliser_nom(p) for p in bruts_prenoms
        if len(normaliser_nom(p)) >= LONGUEUR_MIN_NOM
        and normaliser_nom(p) not in exclus
    }
    PATRONYMES = {
        normaliser_nom(n) for n in bruts_patronymes
        if len(normaliser_nom(n)) >= LONGUEUR_MIN_NOM
        and normaliser_nom(n) not in exclus
    }


def _norm(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    return str(val).strip().lower()


def _parties(email: str) -> tuple:
    if "@" not in email:
        return email, "", ""
    local, domaine = email.split("@", 1)
    ext = domaine.rsplit(".", 1)[-1] if "." in domaine else ""
    return local, domaine, ext


def _sig(niveau: int, code: str, libelle: str, suggestion: str = "") -> dict:
    return {"niveau": niveau, "code": code,
            "libelle": libelle, "suggestion": suggestion}


def detecter_anomalie(email_brut) -> dict:
    """Signalement principal d'un email (le plus grave). S'arrête au premier problème."""
    email = _norm(email_brut)

    if not email:
        return _sig(1, "EMAIL_VIDE", "Champ email absent ou vide")

    if email in PLACEHOLDERS:
        return _sig(1, "PLACEHOLDER",
                    f"Valeur factice saisie à la place d'un email : « {email_brut} »")

    if " " in email or "\t" in email:
        return _sig(1, "ESPACE", "Espace présent dans l'adresse email",
                    email.replace(" ", "").replace("\t", ""))

    if email.count("@") > 1:
        return _sig(1, "MULTI_AROBAS",
                    f"{email.count('@')} caractères @ trouvés — un seul est autorisé")

    if "@" not in email:
        return _sig(1, "MANQUE_AROBAS",
                    "Caractère @ absent — ce n'est pas une adresse email valide")

    local, domaine, ext = _parties(email)

    if not local:
        return _sig(1, "LOCAL_VIDE", "La partie avant @ est vide")

    if not domaine:
        return _sig(1, "DOMAINE_VIDE", "La partie après @ est vide")

    if _RE_INTERDITS.search(email):
        cars = ", ".join(sorted(set(_RE_INTERDITS.findall(email))))
        return _sig(1, "CARACTERE_INTERDIT",
                    f"Caractère(s) interdit(s) dans l'adresse : {cars}")

    if ".." in email:
        return _sig(1, "POINTS_CONSECUTIFS",
                    "Deux points consécutifs présents", email.replace("..", "."))

    if "." not in domaine:
        return _sig(1, "DOMAINE_SANS_POINT",
                    f"Le domaine « {domaine} » n'a pas de point — extension absente")

    if not ext:
        return _sig(1, "EXTENSION_VIDE",
                    "L'adresse se termine par un point — extension manquante")

    if ext in EXTENSIONS_FICHIERS:
        return _sig(1, "EXTENSION_FICHIER",
                    f"« .{ext} » est un format de fichier, pas une extension email")

    if ext in EXTENSIONS_LIEUX:
        return _sig(1, "EXTENSION_LIEU",
                    f"« .{ext} » semble être un nom de lieu saisi à la place d'une extension")

    if ext in TYPOS_EXTENSIONS:
        correction = TYPOS_EXTENSIONS[ext]
        email_corrige = email.rsplit("." + ext, 1)[0] + correction
        return _sig(1, "EXTENSION_TYPO",
                    f"Extension « .{ext} » invalide — probablement « {correction} »",
                    email_corrige)

    if domaine in DOMAINES_INEXISTANTS:
        return _sig(1, "DOMAINE_INEXISTANT",
                    f"Le domaine « @{domaine} » n'existe pas "
                    f"— variante invalide d'un service connu (ex : gmail.fr → gmail.com)")

    if TLDS_VALIDES and ext not in TLDS_VALIDES:
        return _sig(1, "TLD_INEXISTANT",
                    f"L'extension « .{ext} » n'existe pas dans la liste officielle IANA des TLD")

    if domaine in DOMAINES_PERSONNELS:
        return _sig(2, "EMAIL_GRAND_PUBLIC",
                    f"Adresse hébergée chez un service grand public (@{domaine})")

    return _sig(0, "VALIDE", "Aucune anomalie détectée")


_RE_DECOUPE = re.compile(r"[.\-_]+")
_RE_TOKENS = re.compile(r"[.\-_0-9]+")


def _exclu(token: str) -> bool:
    return (token in MOTS_GEOGRAPHIQUES or token in MOTS_COURANTS
            or token in MOTS_GENERIQUES or token in MOTS_METIER
            or token in ABREV_GENERIQUES or token in SIGLES_METIER
            or token in MOTS_FONCTION_DIVERS)


def _est_patronyme_fiable(token: str) -> bool:
    if len(token) < LONGUEUR_MIN_NOM or _exclu(token):
        return False
    return token in PATRONYMES


def _est_prenom_frequent(token: str) -> bool:
    if len(token) < LONGUEUR_MIN_NOM or _exclu(token):
        return False
    return token in PRENOMS


def _contient_mot(base: str, mots_longs: set, mots_courts: set, tokens: list) -> bool:
    for mot in mots_longs:
        if mot in base:
            return True
    for t in tokens:
        if t in mots_courts:
            return True
    return False


def classifier_local_part(local: str) -> str:
    """GENERIQUE > INSTITUTIONNEL > NOMINATIF > NOMINATIF_PARTIEL > INDETERMINE."""
    if not local:
        return "NON_ANALYSE"
    if not PRENOMS and not PATRONYMES:
        return "NON_ANALYSE"

    base = normaliser_nom(local)
    tokens = [t for t in _RE_TOKENS.split(base) if t]

    gen_longs = {m for m in (MOTS_GENERIQUES | MOTS_FONCTION_DIVERS)
                 if len(m) >= LONGUEUR_MIN_SOUSCHAINE}
    gen_courts = ({m for m in MOTS_GENERIQUES if len(m) < LONGUEUR_MIN_SOUSCHAINE}
                  | ABREV_GENERIQUES
                  | {m for m in MOTS_FONCTION_DIVERS if len(m) < LONGUEUR_MIN_SOUSCHAINE})
    if _contient_mot(base, gen_longs, gen_courts, tokens):
        return "GENERIQUE"

    met_longs = {m for m in MOTS_METIER if len(m) >= LONGUEUR_MIN_SOUSCHAINE}
    if _contient_mot(base, met_longs, MOTS_COURTS_METIER, tokens):
        return "INSTITUTIONNEL"

    if _RE_DECOUPE.search(base):
        parts = [t for t in _RE_DECOUPE.split(base) if t]
        prenoms = [t for t in parts if _est_prenom_frequent(t)]
        noms = [t for t in parts if _est_patronyme_fiable(t)]
        initiales = [t for t in parts if len(t) == 1 and t.isalpha()]
        if prenoms and noms:
            return "NOMINATIF"
        if prenoms and initiales:
            return "NOMINATIF"
        if prenoms:
            return "NOMINATIF_PARTIEL"
        if noms and initiales:
            return "NOMINATIF_PARTIEL"
    else:
        if len(base) >= LONGUEUR_MIN_NOM + 1:
            initiale, reste = base[0], base[1:]
            if initiale.isalpha() and _est_patronyme_fiable(reste):
                return "NOMINATIF"
        if _est_prenom_frequent(base):
            return "NOMINATIF_PARTIEL"

    return "INDETERMINE"


def classifier_domaine(domaine: str) -> str:
    if not domaine:
        return "NON_ANALYSE"
    return "PUBLIC" if domaine in DOMAINES_PERSONNELS else "PROPRE"


MOTS_VIDES_CORRESP = {
    "de", "du", "des", "le", "la", "les", "et", "en", "au", "aux",
    "rue", "avenue", "boulevard", "place", "chemin",
    "impasse", "allee", "route", "cours", "quai", "passage",
    "sarl", "sas", "scp", "scm", "selarl", "selas", "eurl",
    "monsieur", "madame", "docteur",
}

LONGUEUR_MIN_MOT_CORRESP = 4


def _mots_significatifs(texte: str) -> set:
    if not texte:
        return set()
    base = normaliser_nom(texte)
    mots = re.split(r"[^a-z]+", base)
    return {m for m in mots
            if len(m) >= LONGUEUR_MIN_MOT_CORRESP and m not in MOTS_VIDES_CORRESP}


def evaluer_correspondance(local_part, raison_principale="",
                           raison_parent="", adresse="",
                           libelle_principal="(EG)", libelle_parent="(EJ parent)") -> str:
    """Correspondance de la partie locale avec la raison sociale (principale ou
    parente) ou l'adresse. La raison parente n'est testée que si la principale échoue."""
    if not local_part:
        return ""

    local_compact = re.sub(r"[^a-z]", "", normaliser_nom(local_part))
    if len(local_compact) < LONGUEUR_MIN_MOT_CORRESP:
        return "Aucune correspondance"

    def _match(mots_ref):
        return any(mot in local_compact for mot in mots_ref)

    mots_principal = _mots_significatifs(raison_principale)
    mots_parent = _mots_significatifs(raison_parent)
    mots_adresse = _mots_significatifs(adresse)

    correspondances = []
    if mots_principal and _match(mots_principal):
        correspondances.append(f"Raison sociale {libelle_principal}")
    elif mots_parent and _match(mots_parent):
        correspondances.append(f"Raison sociale {libelle_parent}")
    if mots_adresse and _match(mots_adresse):
        correspondances.append("Adresse")

    if not correspondances:
        return "Aucune correspondance"
    return " + ".join(correspondances)


def analyser_emails(df: pd.DataFrame, col_email: str = "email_stru") -> pd.DataFrame:
    df = df.copy()
    df["email_norm"] = df[col_email].apply(_norm)

    signalements = df[col_email].apply(detecter_anomalie)
    df["niveau_anomalie"] = signalements.apply(lambda s: s["niveau"])
    df["code_anomalie"] = signalements.apply(lambda s: s["code"])
    df["libelle_anomalie"] = signalements.apply(lambda s: s["libelle"])
    df["suggestion"] = signalements.apply(lambda s: s["suggestion"])

    parties = df["email_norm"].apply(lambda e: _parties(e) if e else ("", "", ""))
    df["local_part"] = parties.apply(lambda p: p[0])
    df["domaine"] = parties.apply(lambda p: p[1])
    df["extension"] = parties.apply(lambda p: p[2])

    masque = (df["niveau_anomalie"] < 1) | (df["code_anomalie"] == "EMAIL_GRAND_PUBLIC")
    df["type_local"] = ""
    df["type_domaine"] = ""
    df.loc[masque, "type_local"] = df.loc[masque, "local_part"].apply(classifier_local_part)
    df.loc[masque, "type_domaine"] = df.loc[masque, "domaine"].apply(classifier_domaine)

    def _affiner_gp(row):
        if row["code_anomalie"] != "EMAIL_GRAND_PUBLIC":
            return row["libelle_anomalie"]
        tl = row["type_local"]
        if tl == "NOMINATIF":
            return (f"Adresse grand public à caractère personnel (@{row['domaine']}) "
                    f"— probablement une personne, pas la structure")
        if tl in ("INSTITUTIONNEL", "GENERIQUE"):
            return (f"Adresse grand public à formulation institutionnelle (@{row['domaine']}) "
                    f"— boîte de la structure sur un service grand public")
        return f"Adresse hébergée chez un service grand public (@{row['domaine']})"

    df["libelle_anomalie"] = df.apply(_affiner_gp, axis=1)
    return df


def marquer_doublons(df: pd.DataFrame,
                     col_email_norm: str = "email_norm",
                     col_id: str = "idstructure_stru") -> pd.DataFrame:
    df = df.copy()
    renseignes = df[df[col_email_norm] != ""]
    n_par_email = renseignes.groupby(col_email_norm)[col_id].transform("nunique")
    df["nb_structures_meme_email"] = n_par_email.fillna(1).astype(int)
    df["est_doublon"] = df["nb_structures_meme_email"] > 1

    masque = df["est_doublon"] & (df["niveau_anomalie"] < 2)
    df.loc[masque, "niveau_anomalie"] = 2
    df.loc[masque, "code_anomalie"] = "DOUBLON"
    df.loc[masque, "libelle_anomalie"] = df.loc[masque, "nb_structures_meme_email"].apply(
        lambda n: f"Email partagé par {n} structures distinctes — vérifier si intentionnel"
    )
    return df


# Détection géographique : ville / département / région portés par la partie locale,
# + concordance stricte avec la commune de la structure. Purement informatif.
# À charger après charger_bases_noms (les collisions ville <-> prénom/patronyme
# sont écartées via PRENOMS/PATRONYMES).

SEUIL_POPULATION_VILLE = 2000
SEUIL_SOUSCHAINE_GEO = 6

VILLES = set()
DEPARTEMENTS = set()
REGIONS = set()
COMMUNE_NOM = {}
COMMUNE_DEP = {}
COMMUNE_REG = {}
DEP_NOM = {}
REG_NOM = {}
DEP_CODE_BY_NOM = {}
REG_CODE_BY_NOM = {}
VILLE_DEPTS = {}

_RE_VILLES = _RE_DEPTS = _RE_REGIONS = None
_VILLES_COURTES = _DEPTS_COURTS = _REGIONS_COURTES = set()


def _compact_geo(texte) -> str:
    return re.sub(r"[^a-z]", "", normaliser_nom(texte or ""))


def _norm_code_commune(code) -> str:
    c = str(code).strip()
    if c.endswith(".0"):
        c = c[:-2]
    return c.zfill(5)


def _build_regex_geo(noms_longs):
    if not noms_longs:
        return None
    motif = "|".join(re.escape(n) for n in sorted(noms_longs, key=len, reverse=True))
    return re.compile("(" + motif + ")")


def charger_geo_insee(df_communes,
                      col_code="code_insee", col_nom="nom_sans_accent",
                      col_dep="dep_code", col_dep_nom="dep_nom",
                      col_reg="reg_code", col_reg_nom="reg_nom",
                      col_pop="population",
                      seuil_population=SEUIL_POPULATION_VILLE):
    """Référentiels géo depuis le fichier communes data.gouv (COG + population)."""
    global VILLES, DEPARTEMENTS, REGIONS
    global COMMUNE_NOM, COMMUNE_DEP, COMMUNE_REG, DEP_NOM, REG_NOM
    global DEP_CODE_BY_NOM, REG_CODE_BY_NOM, VILLE_DEPTS
    global _RE_VILLES, _RE_DEPTS, _RE_REGIONS
    global _VILLES_COURTES, _DEPTS_COURTS, _REGIONS_COURTES

    COMMUNE_NOM, COMMUNE_DEP, COMMUNE_REG, DEP_NOM, REG_NOM = {}, {}, {}, {}, {}
    VILLE_DEPTS = {}
    villes = set()
    collisions = PRENOMS | PATRONYMES
    cols = df_communes.columns

    for _, r in df_communes.iterrows():
        code = _norm_code_commune(r[col_code])
        nom = _compact_geo(r[col_nom])
        dep = str(r[col_dep]).strip()
        reg = str(r[col_reg]).strip()
        COMMUNE_NOM[code] = nom
        COMMUNE_DEP[code] = dep
        COMMUNE_REG[code] = reg
        if nom and dep:
            VILLE_DEPTS.setdefault(nom, set()).add(dep)
        if dep and col_dep_nom in cols:
            DEP_NOM.setdefault(dep, _compact_geo(r[col_dep_nom]))
        if reg and col_reg_nom in cols:
            REG_NOM.setdefault(reg, _compact_geo(r[col_reg_nom]))
        try:
            pop = float(r[col_pop])
        except (TypeError, ValueError):
            pop = 0
        if nom and len(nom) >= 4 and pop >= seuil_population and nom not in collisions:
            villes.add(nom)

    VILLES = villes
    DEPARTEMENTS = {v for v in DEP_NOM.values() if len(v) >= 3}
    REGIONS = {v for v in REG_NOM.values() if len(v) >= 3}
    DEP_CODE_BY_NOM = {nom: code for code, nom in DEP_NOM.items()}
    REG_CODE_BY_NOM = {nom: code for code, nom in REG_NOM.items()}

    _VILLES_COURTES = {n for n in VILLES if len(n) < SEUIL_SOUSCHAINE_GEO}
    _DEPTS_COURTS = {n for n in DEPARTEMENTS if len(n) < SEUIL_SOUSCHAINE_GEO}
    _REGIONS_COURTES = {n for n in REGIONS if len(n) < SEUIL_SOUSCHAINE_GEO}
    _RE_VILLES = _build_regex_geo({n for n in VILLES if len(n) >= SEUIL_SOUSCHAINE_GEO})
    _RE_DEPTS = _build_regex_geo({n for n in DEPARTEMENTS if len(n) >= SEUIL_SOUSCHAINE_GEO})
    _RE_REGIONS = _build_regex_geo({n for n in REGIONS if len(n) >= SEUIL_SOUSCHAINE_GEO})
    return {"villes": len(VILLES), "departements": len(DEPARTEMENTS), "regions": len(REGIONS)}


def _trouver_geo(base_compact, tokens_set, courts, regex):
    inter = tokens_set & courts
    if inter:
        return next(iter(inter))
    if regex is not None:
        m = regex.search(base_compact)
        if m:
            return m.group(1)
    return None


def detecter_geo(local_part, cdcommune=None) -> dict:
    """geo_local (ex. 'Ville (lyon)') + geo_concordant (True/False) vs la commune."""
    vide = {"geo_local": "", "geo_concordant": ""}
    if not local_part:
        return vide

    base = normaliser_nom(local_part)
    base_compact = re.sub(r"[^a-z]", "", base)
    tokens_set = {t for t in re.split(r"[^a-z]+", base) if t}

    v = _trouver_geo(base_compact, tokens_set, _VILLES_COURTES, _RE_VILLES)
    d = _trouver_geo(base_compact, tokens_set, _DEPTS_COURTS, _RE_DEPTS)
    r = _trouver_geo(base_compact, tokens_set, _REGIONS_COURTES, _RE_REGIONS)

    if d and d == v:
        d = None
    if r and (r == v or r == d):
        r = None

    parts = []
    if v:
        parts.append(f"Ville ({v})")
    if d:
        parts.append(f"Département ({d})")
    if r:
        parts.append(f"Région ({r})")
    if not parts:
        return vide

    concord = False
    if cdcommune is not None and str(cdcommune).strip() not in ("", "nan", "None"):
        code = _norm_code_commune(cdcommune)
        dep = COMMUNE_DEP.get(code)
        reg = COMMUNE_REG.get(code)
        if v and dep and dep in VILLE_DEPTS.get(v, set()):
            concord = True
        if d and dep and DEP_CODE_BY_NOM.get(d) == dep:
            concord = True
        if r and reg and REG_CODE_BY_NOM.get(r) == reg:
            concord = True

    return {"geo_local": " + ".join(parts), "geo_concordant": concord}

#!/usr/bin/env python
# coding: utf-8

# """
# Ce module "Utils", contient des fonctions utilitaires pour le matching direct et indirect entre FINESS -> SIRENE
# """

# In[1]:


get_ipython().system('pip install rapidfuzz pathlib')


# In[2]:


from importlib import reload   # recharge automatiquement les MàJ du module.
import Conn_db

reload(Conn_db)


# In[3]:


from Conn_db import get_finess_active, get_sirene_active
from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler
import pandas as pd
from pathlib import Path
import unicodedata
import re
import os


# ### A. Fonctions de normalization des noms de structures et d'adresse:

# In[4]:


# =========================
# Normalisation du texte
# =========================

# Stop words métier 
STOP_WORDS = {
    "DE", "DU", "DES", "LA", "LE", "LES",
    "ET", "EN", "AU", "AUX","L",
    "SA", "SAS", "SARL", "EURL", "SCI", "SELARL", "SELAS", "ASSO"
}

def normalize_text(text):

    if pd.isna(text):
        return ""

    # 1.  enlever caractères invisibles
    text = text.replace("\xa0", " ")
    # 2. enlever accents
    text = unicodedata.normalize("NFKD", text)
    text = "".join([c for c in text if not unicodedata.combining(c)])
    # 3. majuscule
    text = text.upper()
    # 4. enlever ponctuation
    text = re.sub(r"[^\w\s]", " ", text)
    # 5. enlever espaces multiples
    text = re.sub(r"\s+", " ", text).strip()
    # 6. enlever stop words
    words = text.split()
    words = [w for w in words if w not in STOP_WORDS]

    return " ".join(words)


# ===========================
# Normalisation de l'adresse
# ===========================
def normalize_adresse(text):

    if pd.isna(text):
        return ""
    text = text.replace("\xa0", " ")    # enlever caractères invisibles
    text = unicodedata.normalize("NFKD", text)
    text = "".join([c for c in text if not unicodedata.combining(c)])
    text = text.upper()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


#===========================================
# Mapping et enrichissement de type de voie
#===========================================
def map_type_voie(type_voie):

    if pd.isna(type_voie):
        return ""

    # normalisation AVANT mapping
    type_voie = normalize_adresse(type_voie)

    mapping = {
        "ACH": "ANCIEN CHEMIN", "AV": "AVENUE", "ALL": "ALLEE", "AUT": "AUTOROUTE", "BD": "BOULEVARD", "BRG": "BOURG",
        "BCLE": "BOUCLE","CAMP": "CAMP", "CAR": "CARREFOUR", "CARR": "CARRE", "CGNE": "CAMPAGNE", "CCAL": "CENTRE COMMERCIAL","CHE": "CHEMIN","CHEM": "CHEMIN", "CHS": "CHAUSSEE",
        "CHT": "CHATEAU", "CTR": "CENTRE", "CTRE": "CENTRE", "PRV": "PARVIS","PTE": "PORTE", "R": "RUE", "RTE": "ROUTE", "RES": "RESIDENCE", "DOM": "DOMAINE",
        "IMP": "IMPASSE", "PL": "PLACE", "PAS": "PASSAGE", "PASS": "PASSAGE", "STA": "STATION", "QU": "QUAI", "QUA": "QUAI", "ESP": "ESPLANADE",
        "ESPA": "ESPLANADE", "FG": "FAUBOURG", "FOS": "FOSSE", "FOYR": "FOYER", "FRM": "FERME", "SQ" : "SQUARE"
    }
    # remplacement
    return mapping.get(type_voie, type_voie)


# ## B. Mesure des similarités : 2 scores clés

# In[5]:


# -------------------------
# Distance de Levenshtein :
# -------------------------
def levenshtein_score(a, b):
    if not a or not b:
        return 0
    return fuzz.ratio(a, b)

# -------------------------
# Indice de Jaccard
# -------------------------
def jaccard_score(a, b):

    if not a or not b:
        return 0.0

    tokens_a = set(a.split())
    tokens_b = set(b.split())

    union = tokens_a | tokens_b
    if not union:
        return 0.0

    return len(tokens_a & tokens_b) / len(union) * 100  
# -------------------------
# Score global pondéré :
# -------------------------
def compute_text_similarity(a, b):
    if not a or not b:
        return 0.0

    lev = levenshtein_score(a, b)
    jac = jaccard_score(a, b)

    return 0.6 * lev + 0.4 * jac           # Selon la littérature lev est plus robuste que jac



# #### B-1. Mesure de similarité pour noms de structure

# In[6]:


#============================
# 1. Extraction des initiales
#=============================
def get_initials(text):
    """
    Extrait les initiales des mots d'une chaîne.
    Ex : "ASSOCIATION PUPILLES ENSEIGNEMENT PUBLIC" → "APEP"
    """
    if not text:
        return ""

    words = text.split()
    return "".join(word[0] for word in words if word)

#================================
# 2. Score basé sur les initiales
#================================
def initials_score(a, b):
    """
    Calcule un score de similarité basé sur les initiales,
    en couvrant tous les cas d'abréviations.
    """
    if not a or not b:
        return 0.0

    init_a = get_initials(a)
    init_b = get_initials(b)

    # 3 comparaisons complémentaires
    score_init_init = levenshtein_score(init_a, init_b)
    score_init_b = levenshtein_score(init_a, b)
    score_a_init = levenshtein_score(a, init_b)

    return max(score_init_init, score_init_b, score_a_init)

#===================================
# 3. Fonction finale dédiée aux noms
#===================================
def compute_name_similarity(a, b):
    """
    Calcule la similarité entre rs_finess et denom_sirene,
    en combinant :
    - le score textuel classique (Levenshtein + Jaccard)
    - le score basé sur les initiales (abréviations)

    """
    if not a or not b:
        return 0.0

    base_score = compute_text_similarity(a, b)

    n_words_a = len(a.split())
    n_words_b = len(b.split())

    # cas abréviation (1 mot vs plusieurs mots)
    if (n_words_a == 1 and n_words_b > 1) or (n_words_b == 1 and n_words_a > 1):
        init_score = initials_score(a, b)
        return 0.7 * base_score + 0.3 * init_score

    # tous les autres cas → pas d'initiales
    return base_score


# #### B-2. Mesure de similarité pour Adresse

# In[7]:


#=======================================
# Calcul de la similarité global d'adresse
#=======================================
def compute_adresse_similarity(row_fi, row_si):

    # =========================
    # 1. Extraction des champs
    # =========================
    num_fi = row_fi["nmvoie_stru"]
    num_si = row_si["numero_voie"]

    type_fi = row_fi["lbtypevoie_stru"]
    type_si = row_si["type_voie"]

    lib_fi = row_fi["lbvoie_stru"]
    lib_si = row_si["libelle_voie"]

    # =========================
    # Nettoyage (APRÈS extraction)
    # =========================
    type_fi = str(type_fi).strip() if pd.notna(type_fi) else ""
    type_si = str(type_si).strip() if pd.notna(type_si) else ""

    lib_fi = str(lib_fi).strip() if pd.notna(lib_fi) else ""
    lib_si = str(lib_si).strip() if pd.notna(lib_si) else ""

    com_fi = str(row_fi["cdcommune_stru"]).strip()
    com_si = str(row_si["code_commune"]).strip()

    # =========================
    # 2. Similarité numéro: exacte
    # =========================
    if pd.notna(num_fi) and pd.notna(num_si):
        score_num = 100 if str(num_fi) == str(num_si) else 0
    else:
        score_num = 0

    # =========================
    # 3. Similarité commune : exacte
    # =========================
    score_com = 100 if com_fi == com_si else 0

     # =========================
    # 4. type + libellé : similarité approximative
    # =========================

    addr_fi = f"{type_fi} {lib_fi}".strip()
    addr_si = f"{type_si} {lib_si}".strip()

    score_addr = compute_text_similarity(addr_fi, addr_si)
    # =========================
    # 6. Score final pondéré
    # =========================
    score_adresse = (
        0.30 * score_com +
        0.30 * score_num +
        0.40 * score_addr)

    return score_adresse


# ## C. Blocking Sirene par départements : (1 seule fois !!!)

# In[8]:


# =========================
# CONFIG
# =========================
SIRENE_PARQUET_DIR = "/home/jovyan/work/sirenisation_finess/data/sirene_parquets"


# In[9]:


# ======================================
# Créer SIRENE PARQUETs par département (1 fois)
# ======================================

def build_sirene_dep(con_duck, output_dir):
    """
    Crée un fichier parquet par département à partir de sirene_joined.
    - garde toutes les colonnes de sirene_joined
    - ajoute une colonne dep
    - normalise denomination avec normalize_text
    - normalise aussi les champs d'adresse avec normalize_adresse
    - crée aussi un fichier dep_UNK.parquet pour les code_commune manquants
    """

    os.makedirs(output_dir, exist_ok=True)

    print(" Création des parquets SIRENE par département (avec normalisation)...")

    # Liste des départements présents
    deps = con_duck.execute("""
        SELECT DISTINCT
            COALESCE(SUBSTR(code_commune, 1, 2), 'UNK') AS dep
        FROM sirene_joined
    """).fetchall()

    deps = [d[0] for d in deps]

    print(f"{len(deps)} départements détectés")

    for dep in deps:

        # Charger uniquement le département courant
        df = con_duck.execute(f"""
            SELECT
                *,
                COALESCE(SUBSTR(code_commune, 1, 2), 'UNK') AS dep
            FROM sirene_joined
            WHERE COALESCE(SUBSTR(code_commune, 1, 2), 'UNK') = '{dep}'
        """).fetch_df()

        # Normalisation de denomination:
        df["denomination"] = df["denomination"].fillna("").apply(normalize_text)
        # --- DEP ---
        df["dep"] = df["code_commune"].str[:2]
        # Normalisation et enrichissement d'adresse:
        df["type_voie"] = df["type_voie"].apply(map_type_voie)
        df["libelle_voie"] = df["libelle_voie"].apply(normalize_adresse)

        path = os.path.join(output_dir, f"dep_{dep}.parquet")
        df.to_parquet(path, index=False)

    print("✅ SIRENE prête pour blocking")


# In[10]:


# =========================
# LOADER SIRENE (avec cache)
# =========================
class SireneLoader:

    def __init__(self, base_path, max_cache=10):
        self.base_path = base_path
        self.cache = {}
        self.max_cache = max_cache

    def load_dep(self, dep):

        if dep in self.cache:
            return self.cache[dep]

        # limiter le cache (FIFO simple)
        if len(self.cache) >= self.max_cache:
            key_to_remove = next(iter(self.cache))
            if key_to_remove != "UNK":
                self.cache.pop(key_to_remove)

        path = os.path.join(self.base_path, f"dep_{dep}.parquet")

        if not os.path.exists(path):
            self.cache[dep] = None
            return None

        df = pd.read_parquet(path)
        self.cache[dep] = df

        return df


# In[11]:


# --- Blocking par dep ----

def get_sirene_block_for_row(row, sirene_loader):

    dep = row.get("dep")

    if dep is None or str(dep).lower() == "nan":
        dep = "UNK"
    else:
        dep = str(dep).zfill(2)

    # charger fichier UNKNOWN (toujours utile)
    df_unk = sirene_loader.load_dep("UNK")

    # Si pas de département côté FINESS
    if not dep:
        return df_unk

    # Sinon charger département correspondant
    df_dep = sirene_loader.load_dep(dep)

    # cas 1 : département existe
    if df_dep is not None and not df_dep.empty:

        # concat dep + unknown
        if df_unk is not None and not df_unk.empty:
            return pd.concat([df_dep, df_unk], ignore_index=True)

        return df_dep

    # cas 2 : département non trouvé côté SIRENE → fallback UNKNOWN
    return df_unk


# In[12]:


"""
# Génerer les parquets siren par dep 

con_duck = get_sirene_active(read_only=True)
build_sirene_dep(con_duck, SIRENE_PARQUET_DIR)
"""


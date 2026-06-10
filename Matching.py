#!/usr/bin/env python
# coding: utf-8

# In[1]:


get_ipython().system('pip install rapidfuzz XlsxWriter')


# In[2]:


from importlib import reload   # recharge automatiquement les MàJ du module.
import Conn_db
import Utils as ul

reload(Conn_db)
reload(ul)


# In[3]:


from Conn_db import get_finess_active, get_sirene_active
import Utils as ul
import pandas as pd
import os


# ### Bloc A — Matching direct:Finess avec num siren (Phase 1)

# #### 1. RÉCUPÉRER LES DUPLICATS FINESS

# In[4]:


def get_finess_with_siren(conn):

    query = """
    SELECT
        idstructure_stru,
        nmfinessej_stru,
        nmsiren_stru AS siren,
        raisonsociale_stru,
        cdcommune_stru,

        -- adresse FINESS
        nmvoie_stru,
        lbtypevoie_stru,
        lbvoie_stru

    FROM BICOEUR_DWH_SNAPSHOT.dbo.dwh_structure
    WHERE topsource_stru = 'FINESS'
      AND typeidpm_stru = 'EJ'
      AND (
            dtfermestruct_stru IS NULL
            OR dtfermestruct_stru >= SYSDATETIME()
      )
      AND nmsiren_stru IS NOT NULL
    """

    df = pd.read_sql(query, conn)
    print("Nombre de Finess ayant un num_siren :", len(df))
    print("Nombre de SIREN distincts :", df["siren"].nunique())
    return df


# #### 2. Normalisation Finess

# In[5]:


def preprocess_finess(df):
    df = df.copy()

    # normalisation raison sociale
    df["raisonsociale_stru"] = df["raisonsociale_stru"].apply(ul.normalize_text)

    # normalisation adresse
    df["lbtypevoie_stru"] = df["lbtypevoie_stru"].apply(ul.map_type_voie)
    df["lbvoie_stru"] = df["lbvoie_stru"].apply(ul.normalize_adresse)

    # extraction département
    df["dep"] = df["cdcommune_stru"].astype(str).str[:2]

    return df


# #### 3. Récupérer la référence Sirene

# In[6]:


def get_sirene_dict(con_duck, siren_list):

    if not siren_list:
        return {}

    placeholders = ",".join(["?"] * len(siren_list))

    query = f"""
    SELECT
        siren,
        denomination,
        code_commune,
        numero_voie,
        type_voie,
        libelle_voie,
        adresse_complete
    FROM sirene_joined
    WHERE siren IN ({placeholders})
    """

    df = con_duck.execute(query, siren_list).fetch_df()

    # normalisation robuste
    df["denomination"] = df["denomination"].apply(lambda x: ul.normalize_text(x) if pd.notna(x) else "")
    df["type_voie"] = df["type_voie"].apply(lambda x: ul.map_type_voie(x) if pd.notna(x) else "")
    df["libelle_voie"] = df["libelle_voie"].apply(lambda x: ul.normalize_adresse(x) if pd.notna(x) else "")

    return df.set_index("siren").to_dict("index")


# #### 4. MATCHING DIRECT :

# In[7]:


def process_direct_matching(finess_df, sirene_dict, threshold=67):
    """
    Phase 1 - Matching direct FINESS vs SIRENE via SIREN

    Pour chaque ligne FINESS :
    - récupération de la référence SIRENE via le SIREN
    - calcul des scores (nom + adresse)
    - calcul d’un score global pondéré
    - application des règles de validation :
        1. score_global >= threshold
        2. OU (score_nom >= 15 ET score_adresse >= 55)

    Retourne :
    - valid_df : correspondances validées
    - rejected_df : correspondances rejetées
    """

    valid_records = []
    rejected_records = []

    # =========================
    # Boucle principale
    # =========================
    for _, row in finess_df.iterrows():

        siren = row["siren"]
        ref = sirene_dict.get(siren)

        row_out = row.copy()

        # =========================
        # 1. Cas : SIREN absent côté SIRENE
        # =========================
        if ref is None:
            row_out["score_nom"] = None
            row_out["score_adresse"] = None
            row_out["score_global"] = None
            row_out["statut"] = "REJET"
            row_out["motif"] = "SIREN absent dans SIRENE"

            rejected_records.append(row_out)
            continue

        # =========================
        # 2. Calcul des scores
        # =========================

        # Similarité des noms
        score_nom = ul.compute_name_similarity(
            row["raisonsociale_stru"],
            ref["denomination"]
        )

        # Similarité des adresses
        score_adresse = ul.compute_adresse_similarity(
            row_fi=row,
            row_si=ref
        )

        # Score global pondéré
        score_global = 0.4 * score_nom + 0.6 * score_adresse

        # =========================
        # 3. Enrichissement des données SIRENE
        # =========================
        row_out["denomination_sirene"] = ref["denomination"]
        row_out["code_commune_sirene"] = ref["code_commune"]

        # Reconstruction adresse SIRENE (normalisée)
        num_si = str(ref.get("numero_voie") or "").strip()
        type_si = str(ref.get("type_voie") or "").strip()
        lib_si = str(ref.get("libelle_voie") or "").strip()

        adresse_sirene = " ".join([x for x in [num_si, type_si, lib_si] if x])
        adresse_sirene = " ".join(adresse_sirene.split())

        row_out["adresse_sirene"] = adresse_sirene

        # =========================
        # 4. Stockage des scores
        # =========================
        row_out["score_nom"] = round(score_nom, 2)
        row_out["score_adresse"] = round(score_adresse, 2)
        row_out["score_global"] = round(score_global, 2)

        # =========================
        # 5. Validation finale
        # =========================
        # Règle 1 : seuil global
        # Règle 2 : rattrapage (nom faible mais adresse forte)
        if score_global >= threshold:
            row_out["statut"] = "VALID"
            row_out["motif"] = "Score global >= seuil"
            valid_records.append(row_out)

        elif score_nom >= 15 and score_adresse >= 55:
            row_out["statut"] = "VALID"
            row_out["motif"] = "adresse forte"
            valid_records.append(row_out)

        else:

            row_out["statut"] = "REJET"

            # cas particulier : nom parfait mais adresse faible
            if score_nom >= 80 and score_adresse < 50:
                row_out["motif"] = "Problème d’adresse"

            else:
                row_out["motif"] = "Correspondance faible"

            rejected_records.append(row_out)

    # =========================
    # 6. Conversion en DataFrame
    # =========================
    valid_df = pd.DataFrame(valid_records)
    rejected_df = pd.DataFrame(rejected_records)

    return valid_df, rejected_df


# #### 5. Exportation des résultats en excel:

# In[8]:


def export_matching_excel(valid_df, rejected_df, output_path="matching_phase1.xlsx"):

    print("Total lignes :", len(valid_df) + len(rejected_df))

    if os.path.exists(output_path):
        os.remove(output_path)

    # =========================
    # Flag doublons + rang uniquement pour doublons
    # =========================
    valid_df = valid_df.copy()

    # flag doublons
    valid_df["is_duplicated_siren"] = valid_df.duplicated("siren", keep=False)

    # tri pour cohérence visuelle
    valid_df = valid_df.sort_values(
        by=["siren", "score_global"],
        ascending=[True, False]
    )

    # initialiser colonne rang
    valid_df["rang_siren"] = None

    # calcul rang uniquement pour doublons
    mask_dups = valid_df["is_duplicated_siren"]

    valid_df.loc[mask_dups, "rang_siren"] = (
        valid_df[mask_dups]
        .groupby("siren")["score_global"]
        .rank(method="first", ascending=False)
        .astype(int)
    )

    # =========================
    # Export Excel
    # =========================
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:

        valid_df.to_excel(writer, sheet_name="Matching_validé", index=False)
        rejected_df.to_excel(writer, sheet_name="Matching_rejeté", index=False)

        # synthèse
        synthese = pd.DataFrame({
            "Statut": ["VALID", "REJET"],
            "Nombre": [len(valid_df), len(rejected_df)]
        })

        synthese["Pourcentage"] = synthese["Nombre"] / synthese["Nombre"].sum()
        synthese.to_excel(writer, sheet_name="Synthese", index=False)

    print("Excel généré :", output_path)


# #### 6. Pipeline complet_phase1 : run_direct_matching

# In[9]:


def run_direct_matching(conn_sql, con_duck, export_excel=True, threshold=None):

    print("Phase 1 - Matching direct")

    print("1. Chargement des FINESS avec SIREN...")
    finess_df = get_finess_with_siren(conn_sql)

    print("2. Préprocessing...")
    finess_df = preprocess_finess(finess_df)

    print("3. Chargement des références SIRENE...")
    siren_list = finess_df["siren"].unique().tolist()
    sirene_dict = get_sirene_dict(con_duck, siren_list)

    # valeur par défaut si non fournie
    if threshold is None:
        threshold = 67

    print("4. Matching direct...")
    valid_df, rejected_df = process_direct_matching(
        finess_df,
        sirene_dict,
        threshold=threshold
    )

    print("Threshold utilisé :", threshold)

    print("Matching terminé")
    print(f"Validés : {len(valid_df)}")
    print(f"Rejetés : {len(rejected_df)}")

    if export_excel:
        export_matching_excel(valid_df, rejected_df)

    return valid_df, rejected_df


# ## Bloc B — Matching indirect : Finess -> Sirene (Phase 2)

# #### 1. Lecture Finess par département

# In[10]:


def get_finess_departments(conn_sql):
    query = """
    SELECT DISTINCT LEFT(CAST(cdcommune_stru AS VARCHAR(10)), 2) AS dep
    FROM BICOEUR_DWH_SNAPSHOT.dbo.dwh_structure
    WHERE topsource_stru = 'FINESS'
      AND typeidpm_stru = 'EJ'
      AND (
            dtfermestruct_stru IS NULL
            OR dtfermestruct_stru >= SYSDATETIME()
      )
      AND cdcommune_stru IS NOT NULL
    ORDER BY dep
    """

    deps_df = pd.read_sql(query, conn_sql)
    deps = deps_df["dep"].astype(str).tolist()
    return deps   #récupére la liste des départements présents dans Finess


# #### 2. Prétraitement Finess (Chunk)

# In[11]:


def preprocess_finess_chunk(df):

    df = df.copy()

    # normalisation nom
    df["raison_sociale"] = df["raison_sociale"].fillna("").apply(ul.normalize_text)

    # normalisation adresse
    df["lbtypevoie_stru"] = df["lbtypevoie_stru"].apply(ul.map_type_voie)
    df["lbvoie_stru"] = df["lbvoie_stru"].apply(ul.normalize_adresse)

    # sécurisation code commune
    df["cdcommune_stru"] = df["cdcommune_stru"].astype(str)

    # extraction département
    df["dep"] = df["cdcommune_stru"].astype(str).str[:2].fillna("UNK")

    return df


# #### 3. Préparation du dataset Finess non traité pour la phase 2

# In[12]:


def get_finess_by_department_chunks(conn_sql, dep, valid_df, chunk_size=5000):

    id_col = "nmfinessej_stru"

    # =========================
    # FINESS validés (phase 1)
    # =========================
    valid_ids = set(valid_df[id_col].astype(str)) if valid_df is not None and not valid_df.empty else set()

    # =========================
    # Requête SQL
    # =========================
    query = f"""
    SELECT
        nmfinessej_stru,
        nmsiren_stru AS siren_finess,
        raisonsociale_stru AS raison_sociale,
        cdcommune_stru,

        -- adresse
        nmvoie_stru,
        lbtypevoie_stru,
        lbvoie_stru

    FROM BICOEUR_DWH_SNAPSHOT.dbo.dwh_structure
    WHERE topsource_stru = 'FINESS'
      AND typeidpm_stru = 'EJ'
      AND (
            dtfermestruct_stru IS NULL
            OR dtfermestruct_stru >= SYSDATETIME()
      )
      AND LEFT(CAST(cdcommune_stru AS VARCHAR(10)), 2) = '{dep}'
    """

    # =========================
    # Lecture chunk
    # =========================
    for chunk in pd.read_sql(query, conn_sql, chunksize=chunk_size):

        # sécurisation clé
        chunk[id_col] = chunk[id_col].astype(str)

        # =========================
        # Préprocessing
        # =========================
        chunk = preprocess_finess_chunk(chunk)

        # =========================
        # FILTRAGE PHASE 2 
        # =========================
        chunk = chunk[~chunk[id_col].isin(valid_ids)]             # filtre les finess validés dans phase 1


        if not chunk.empty:
            yield chunk


# #### 4. Récupérer les Top 3 du matching

# In[24]:


def match_top3(row, sirene_loader, top_k=3):
    """
    Cette fonction :
    - réalise le matching entre une structure FINESS et les candidats SIRENE du même département
    - applique un préfiltrage léger pour accélérer le calcul
    - propose les TOP K (par défaut 3) meilleurs candidats SIRENE
    Aucun filtrage métier strict ici → la validation finale se fait à l'export
    """

    # =========================
    # 1. Chargement du bloc SIRENE (blocking par dep)
    # =========================
    row_dict = row._asdict()  # converti la ligne finess en un dictionnaire

    sirene_df = ul.get_sirene_block_for_row(row_dict, sirene_loader)  #Bloching par dep

    # Si aucun candidat SIRENE trouvé dans ce bloc 
    if sirene_df is None or sirene_df.empty:
        return []

    sirene_records = sirene_df.itertuples(index=False)

    finess_name = row.raison_sociale
    if not finess_name:
        return []

    # =========================
    # 2. Construction adresse FINESS (déjà normalisée)
    # =========================
    num = str(row.nmvoie_stru or "").strip()
    type_v = str(row.lbtypevoie_stru or "").strip()
    lib = str(row.lbvoie_stru or "").strip()

    adresse_finess = " ".join([x for x in [num, type_v, lib] if x])

    # =========================
    # 3. SCORING + PREFILTRE 
    # =========================
    results_tmp = []

    for candidate in sirene_records:

        # ---- 3.1 Préfiltre rapide (évite calculs coûteux)
        if ul.levenshtein_score(finess_name, candidate.denomination) < 10:
            continue

        # ---- 3.2 Score nom
        score_nom = ul.compute_name_similarity(
            finess_name,
            candidate.denomination)

        # FILTRE AVANT ADRESSE (CRITIQUE)
        if score_nom < 20:
            continue

        # ---- 3.3 Score adresse
        score_adresse = ul.compute_adresse_similarity(
            row_fi=row_dict,
            row_si=candidate._asdict() )

        # ---- 3.4 2éme Préfiltre léger 
        # On élimine uniquement les cas très faibles
        if score_nom < 30 and score_adresse < 50:
            continue

        # ---- 3.5 Score global (pour ranking final)
        score_global = 0.4 * score_nom + 0.6 * score_adresse

        results_tmp.append((score_global, score_nom, score_adresse, candidate))

    # Aucun candidat crédible après préfiltre => on retourne une val vide
    if not results_tmp:
        return []

    # =========================
    # 4. Sélection des TOP K candidats
    # =========================
    top = sorted(results_tmp, key=lambda x: x[0], reverse=True)[:top_k]

    # =========================
    # 5. Construction du résultat final
    # =========================
    results = []

    for rank, (score_global, score_nom, score_adresse, r) in enumerate(top, start=1):

        # =========================
        # Construction adresse SIRENE (normalisée)
        # =========================
        adresse_sirene = " ".join([
            str(getattr(r, "numero_voie", "") or "").strip(),
            str(getattr(r, "type_voie", "") or "").strip(),
            str(getattr(r, "libelle_voie", "") or "").strip()
        ])

        adresse_sirene = " ".join(adresse_sirene.split())  # nettoyage espaces

        results.append({
            "nmfinessej_stru": row.nmfinessej_stru,
            "siren_finess": row.siren_finess,
            "raison_sociale": finess_name,
            "cdCommune_finess": row.cdcommune_stru,
            "adresse_finess": adresse_finess,

            "siren_ref": r.siren,
            "denomination_sirene": r.denomination,
            "cdCommune_sirene": getattr(r, "code_commune", None),
            "adresse_sirene": adresse_sirene,

            # scores (arrondis pour lisibilité)
            "score_nom": round(score_nom, 2),
            "score_adresse": round(score_adresse, 2),
            "score_global": round(score_global, 2),

            "rang": rank
        })

    return results


# #### 5. Traitemet de chunks pour la phase 2

# In[25]:


from tqdm.auto import tqdm  # ajoute une barre de progression du script en temps réel.

def process_chunk_phase2(chunk, sirene_loader, dep=None, part_idx=None):

    results = []

    desc = f"Phase 2"
    if dep is not None and part_idx is not None:
        desc = f"Dep {dep} - chunk {part_idx}"

    for row in tqdm(
        chunk.itertuples(index=False, name="FinessRow"),
        total=len(chunk),
        desc=desc
    ):
        matches = match_top3(row, sirene_loader)

        if matches:
            results.extend(matches)

    return results


# #### 6. Sauvegarde des résultats au fur et à mesure

# In[26]:


def save_phase2_results(results, output_dir, dep, part_idx):
    if not results:
        return None

    os.makedirs(output_dir, exist_ok=True)

    df_part = pd.DataFrame(results)

    output_path = os.path.join(output_dir, f"phase2_dep_{dep}_part_{part_idx}.parquet")
    df_part.to_parquet(output_path, index=False)

    return output_path


# #### 7. Petit fichier de checkpoint pour reprise

# In[27]:


#---- Garde l'historique des dèpartements déjà traités ----

def load_processed_departments(checkpoint_file):
    if not os.path.exists(checkpoint_file):
        return set()

    with open(checkpoint_file, "r") as f:
        return set(line.strip() for line in f if line.strip())


# In[28]:


def mark_department_done(dep, checkpoint_file):
    with open(checkpoint_file, "a") as f:
        f.write(f"{dep}\n")
        f.flush()   # important


# #### 8. Concaténation final en excel

# In[3]:


def merge_phase2_parquets_to_excel(
    input_dir="phase2_results_by_dep",
    output_excel="matching_phase2_final.xlsx"
):
    """
    Cette fonction :
    - concatène les résultats de matching indirect dans un seul DataFrame
    - trie les candidats par structure FINESS et score décroissant
    - applique la logique métier de validation
    - sépare les résultats en 2 feuilles Excel :
        1. Candidats_valides  : structures FINESS ayant au moins 1 bon candidat
        2. Candidats_rejetes  : structures FINESS n'ayant aucun bon candidat

    Logique métier :
    - un candidat est considéré comme "bon" si :
        score_global >= 67
        OU (score_nom >= 50 ET score_adresse >= 75)
    """
    # =========================
    # 1. Récupération des fichiers parquet
    # =========================
    files = [
        os.path.join(input_dir, f)
        for f in os.listdir(input_dir)
        if f.endswith(".parquet")
    ]

    if not files:
        print("Aucun fichier parquet trouvé")
        return None

    print(f"{len(files)} fichiers parquet détectés")

    # =========================
    # 2. Chargement et concaténation
    # =========================
    dfs = [pd.read_parquet(f) for f in sorted(files)]
    final_df = pd.concat(dfs, ignore_index=True)

    if final_df.empty:
        print("Aucune donnée à exporter")
        return None

    print(f"Total lignes : {len(final_df)}")

    # =========================
    # 3. Tri global
    # =========================
    # Tri par structure FINESS puis par score décroissant
    # pour garder une lecture claire des top candidats
    final_df = final_df.sort_values(
        by=["nmfinessej_stru", "score_global"],
        ascending=[True, False]
    ).copy()

    # =========================
    # 3bis. Ajout du département
    # =========================
    final_df["dep"] = final_df["cdCommune_finess"].fillna("").astype(str).str[:2]
    final_df["dep"] = final_df["dep"].replace("", "UNK")

    # =========================
    # Conversion des scores en float
    # =========================
    for col in ["score_nom", "score_adresse", "score_global"]:
        final_df[col] = (
            final_df[col]
            .astype(str)
            .str.replace(",", ".", regex=False)
            .astype(float)
        )

    # =========================
    # 4. Règles de validation métier
    # =========================
    # Un bon candidat = candidat crédible selon les règles validées
    final_df["bon_candidat"] = (
        (final_df["score_global"] >= 67)
        | (
            (final_df["score_nom"] >= 50)
            & (final_df["score_adresse"] >= 75)) )

    # =========================
    # 5. Décision au niveau structure FINESS
    # =========================
    # Si au moins un candidat est valide pour une structure FINESS,
    # alors on considère que cette structure a un "bon_candidat"
    final_df["has_valid_candidate"] = final_df.groupby("nmfinessej_stru")[
        "bon_candidat"
    ].transform("max")

    # =========================
    # 6. Séparation des jeux d'export
    # =========================
    df_valid = final_df[final_df["has_valid_candidate"]].copy()
    df_reject = final_df[~final_df["has_valid_candidate"]].copy()

    df_valid["motif"] = "bon_candidat"
    df_reject["motif"] = "mauvais_candidat"

    # =========================
    # 7. Synthèse simple
    # =========================
    nb_finess_total = final_df["nmfinessej_stru"].nunique()
    nb_finess_valid = df_valid["nmfinessej_stru"].nunique()
    nb_finess_reject = df_reject["nmfinessej_stru"].nunique()

    synthese = pd.DataFrame({
        "categorie": [
            "structures_finess_total",
            "structures_finess_avec_bon_candidat",
            "structures_finess_sans_bon_candidat",
            "lignes_valides_exportees",
            "lignes_rejetees_exportees"
        ],
        "valeur": [
            nb_finess_total,
            nb_finess_valid,
            nb_finess_reject,
            len(df_valid),
            len(df_reject)
        ]
    })

    # =========================
    # 8. Export Excel
    # =========================
    with pd.ExcelWriter(output_excel, engine="openpyxl") as writer:
        df_valid.to_excel(writer, sheet_name="Candidats_valides", index=False)
        df_reject.to_excel(writer, sheet_name="Candidats_rejetes", index=False)
        synthese.to_excel(writer, sheet_name="Synthese", index=False)

    print(f"Excel généré : {output_excel}")
    print(f"Structures avec bon candidat : {nb_finess_valid}")
    print(f"Structures sans aucun bon candidat : {nb_finess_reject}")

    return {
        "final_df": final_df,
        "df_valid": df_valid,
        "df_reject": df_reject,
        "synthese": synthese
    }


# #### 9. PIPELINE GLOBAL PHASE 2

# In[4]:


def run_indirect_matching_by_department(
    conn_sql,
    valid_df,
    sirene_loader,
    output_dir="phase2_results_by_dep",
    checkpoint_file="phase2_results_by_dep/departments_done.txt",
    chunk_size=5000):

    print("Phase 2 - Matching indirect par département")

    # =========================
    # 1. Préparation dossier
    # =========================
    os.makedirs(output_dir, exist_ok=True)

    # =========================
    # 2. Chargement des départements
    # =========================
    deps = get_finess_departments(conn_sql)
    done_deps = load_processed_departments(checkpoint_file)

    print("Départements déjà traités :", done_deps)

    # =========================
    # 3. Boucle principale
    # =========================
    for dep in deps:

        if dep in done_deps:
            print(f"Département {dep} déjà traité → skip")
            continue

        print(f"\n===== Traitement du département {dep} =====")

        total_results_dep = 0
        part_idx = 0
        dep_success = True

        # =========================
        # 4. Traitement des chunks
        # =========================
        for chunk in get_finess_by_department_chunks(
            conn_sql,
            dep,
            valid_df,
            chunk_size=chunk_size
        ):
            try:
                print(f"Dep {dep} - chunk {part_idx} - {len(chunk)} lignes")

                # vérifier chunk non vide
                if chunk is None or chunk.empty:
                    print("Chunk vide → skip")
                    part_idx += 1
                    continue

                # =========================
                # Matching
                # =========================
                results = process_chunk_phase2(
                    chunk,
                    sirene_loader,
                    dep=dep,
                    part_idx=part_idx)

                # =========================
                # Sauvegarde
                # =========================
                if results:
                    saved_file = save_phase2_results(
                        results,
                        output_dir,
                        dep,
                        part_idx
                    )

                    total_results_dep += len(results)
                    print(f"Résultats écrits : {saved_file} ({len(results)} lignes)")
                else:
                    print("Aucun résultat pour ce chunk")

                part_idx += 1

            except Exception as e:
                print(f"Erreur sur dep {dep}, chunk {part_idx} : {e}")
                dep_success = False
                break

        # =========================
        # 5. Checkpoint
        # =========================
        if dep_success:
            mark_department_done(dep, checkpoint_file)
            print(f"Département {dep} enregistré comme terminé ({total_results_dep} résultats)")
        else:
            print(f"Département {dep} NON terminé (sera repris au prochain run)")

    print("Phase 2 terminée")


# In[ ]:





import json
import pandas as pd

from datetime import datetime


# ============================================================
# Construction du code activité
# ============================================================

def construire_code_activite(nature):
    code_nature = nature.get("codeNature")
    spec = nature.get("caracteristiquesSpecifiques", {})

    if code_nature in ["AASA", "ASR"]:
        key = "typeActiviteAASA" if code_nature == "AASA" else "typeActiviteASR"
        t = spec.get(key, {})

        return "_".join([
            code_nature,
            t.get("activiteSanitaireRegulee", ""),
            t.get("modaliteActivite", ""),
            t.get("formeActivite", "")
        ])

    if code_nature == "EML":
        t = spec.get("typeActiviteEML", {})

        return "_".join([
            code_nature,
            t.get("typeEmlId", "")
        ])

    if code_nature == "ASDR":
        t = spec.get("typeActiviteASDR", {})

        return "_".join([
            code_nature,
            t.get("activiteSanitaireDiverseRegulee", ""),
            t.get("modeFonctionnement", ""),
            t.get("public", "")
        ])

    if code_nature in ["ASOCR", "AMSR"]:
        key = (
            "typeActiviteASOCR"
            if code_nature == "ASOCR"
            else "typeActiviteAMSR"
        )

        t = spec.get(key, {})

        return "_".join([
            code_nature,
            t.get("activiteSocialeRegulee", ""),
            t.get("modeFonctionnement", ""),
            t.get("public", "")
        ])

    if code_nature == "AER":
        t = spec.get("typeActiviteAER", {})

        return "_".join([
            code_nature,
            t.get("activiteEnseignementRegulee", ""),
            t.get("modeFonctionnement", ""),
            t.get("public", "")
        ])

    if code_nature == "AMF":
        t = spec.get("typeActiviteAMF", {})

        return "_".join([
            code_nature,
            t.get("activiteAMF", ""),
            t.get("modaliteActivite", ""),
            t.get("formeActivite", "")
        ])

    if code_nature == "AMM":
        t = spec.get("typeActiviteAMM", {})

        return "_".join([
            code_nature,
            t.get("activiteAMM", ""),
            t.get("modaliteAMM", ""),
            t.get("mentionAMM", ""),
            t.get("ptsAMM", ""),
            t.get("declarationAMM", "")
        ])

    return code_nature


# ============================================================
# Gestion AppAMM
# ============================================================

def construire_code_appamm(app):

    return "_".join([
        "AppAMM",
        str(app.get("typeAppareilAMM", "") or ""),
        str(app.get("statutAppareilAMM", "") or ""),
        str(app.get("nombreAppareilAMM", "0") or "0")
    ])


# ============================================================
# Calcul du statut activité
# ============================================================

def extraire_statut(activite):

    generiques = activite.get(
        "caracteristiquesGeneriques",
        {}
    )

    etat = generiques.get("etatObjet")

    if etat == "I":
        return 3

    evenements = activite.get("evenement", [])

    evenements = [
        ev for ev in evenements
        if str(ev.get("codeEvenement")) in ["12", "15"]
    ]

    def date_evenement(ev):

        try:
            return datetime.fromisoformat(
                ev.get("dateEvenement").replace(
                    "Z",
                    "+00:00"
                )
            )
        except Exception:
            return datetime.min

    evenements.sort(
        key=date_evenement,
        reverse=True
    )

    if evenements and str(
        evenements[0].get("codeEvenement")
    ) == "12":
        return 1

    return 2


# ============================================================
# Gestion des capacités
# ============================================================

def est_capacite_totale(capacite):

    return not any([
        capacite.get("modeFinancement"),
        capacite.get("habilitation"),
        capacite.get("typeLogement"),
        capacite.get("genre")
    ])


def extraire_capacite(capacites, statut):

    total = 0

    for capacite in capacites or []:

        if not est_capacite_totale(capacite):
            continue

        if capacite.get(
            "statutCapacite"
        ) == statut:

            try:
                total += int(
                    capacite.get(
                        "nombre",
                        0
                    )
                )
            except Exception:
                pass

    return total


# ============================================================
# Transformation JSON -> table
# ============================================================

def transformer_json_en_table(json_data):

    lignes = []

    date_maj = json_data.get("generatedAt")

    if date_maj:

        date_maj = datetime.fromisoformat(
            date_maj.replace(
                "Z",
                "+00:00"
            )
        ).strftime("%Y-%m-%d")


    for pmej in json_data.get("pmej", []):

        finess_pmej = pmej.get("numFiness")

        autorisations = {}

        for autorisation in pmej.get(
            "activitesAutorisees",
            []
        ):

            identifiant = autorisation.get(
                "caracteristiquesGeneriques",
                {}
            ).get(
                "activiteAeId"
            )

            if identifiant:
                autorisations[identifiant] = autorisation


        for ege in pmej.get("ege", []):

            finess_ege = ege.get(
                "numFinessEge"
            )


            for activite in ege.get(
                "activitesExercees",
                []
            ):

                nature = activite.get(
                    "nature",
                    {}
                )

                code_nature = nature.get(
                    "codeNature"
                )

                identifiant_autorisation = activite.get(
                    "caracteristiquesGeneriques",
                    {}
                ).get(
                    "identifiantAutorisation"
                )


                autorisation = autorisations.get(
                    identifiant_autorisation
                )


                ligne = {

                    "date_maj": date_maj,

                    "activite_finess_pmej":
                        finess_pmej,

                    "activite_finess_ege":
                        finess_ege,

                    "activite_nature":
                        code_nature,

                    "activite_code":
                        construire_code_activite(
                            nature
                        ),

                    "activite_statut":
                        extraire_statut(
                            activite
                        ),

                    "activite_capacite_installee":
                        extraire_capacite(
                            activite.get(
                                "capacite"
                            ),
                            "09"
                        ),

                    "activite_capacite_autorisee":
                        extraire_capacite(
                            autorisation.get(
                                "capacite"
                            ) if autorisation else [],
                            "01"
                        )
                }

                lignes.append(ligne)


                # Cas AppAMM
                if code_nature == "AMM":

                    appareils = nature.get(
                        "caracteristiquesSpecifiques",
                        {}
                    ).get(
                        "appareil",
                        []
                    )

                    for appareil in appareils:

                        lignes.append({

                            **ligne,

                            "activite_nature":
                                "AppAMM",

                            "activite_code":
                                construire_code_appamm(
                                    appareil
                                )
                        })


    return lignes


# ============================================================
# Programme principal
# ============================================================

if __name__ == "__main__":

    with open(
        "input.json",
        encoding="utf-8"
    ) as fichier:

        data = json.load(fichier)


    resultat = transformer_json_en_table(
        data
    )


    dataframe = pd.DataFrame(
        resultat
    )


    dataframe.to_csv(
        "activites.csv",
        index=False,
        encoding="utf-8"
    )


    print(
        dataframe
    )
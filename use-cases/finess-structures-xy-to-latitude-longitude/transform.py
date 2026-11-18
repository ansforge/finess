"""
Latitude et longitude des adresses du flux Structures FiNESS+ à partir de leurs coordonnées planes.

Usage :
    python transform.py [flux en entrée] [CSV en sortie]

Par défaut : input.json et coordonnees.csv. Le flux peut être compressé (.json.gz) ;
il est lu au fil de l'eau, sans être chargé en mémoire. Aucune dépendance hors de la
bibliothèque standard de Python.
"""

import csv
import gzip
import json
import math
import re
import sys


# ============================================================
# Lambert 93 (RGF93, EPSG:2154) vers latitude et longitude
# Projection conique conforme de Lambert, formules de l'IGN
# ============================================================

L93_N = 0.7256077650532670
L93_C = 11754255.426096
L93_XS = 700000.0
L93_YS = 12655612.049876
L93_E = 0.0818191910428158
L93_MERIDIEN = math.radians(3.0)


def lambert93_vers_latitude_longitude(x, y):
    rayon = math.hypot(x - L93_XS, y - L93_YS)
    gamma = math.atan((x - L93_XS) / (L93_YS - y))
    latitude_isometrique = -math.log(abs(rayon / L93_C)) / L93_N

    phi = 2 * math.atan(math.exp(latitude_isometrique)) - math.pi / 2
    for _ in range(8):
        s = L93_E * math.sin(phi)
        phi = 2 * math.atan(
            ((1 + s) / (1 - s)) ** (L93_E / 2) * math.exp(latitude_isometrique)
        ) - math.pi / 2

    return math.degrees(phi), math.degrees(L93_MERIDIEN + gamma / L93_N)


# ============================================================
# UTM sur l'ellipsoïde GRS 80 vers latitude et longitude
# Mercator transverse, série de Krüger à l'ordre 3
# ============================================================

APLATISSEMENT = 1 / 298.257222101
N = APLATISSEMENT / (2 - APLATISSEMENT)
RAYON = 6378137.0 / (1 + N) * (1 + N ** 2 / 4 + N ** 4 / 64)
BETA = (
    N / 2 - 2 * N ** 2 / 3 + 37 * N ** 3 / 96,
    N ** 2 / 48 + N ** 3 / 15,
    17 * N ** 3 / 480,
)
DELTA = (
    2 * N - 2 * N ** 2 / 3 - 2 * N ** 3,
    7 * N ** 2 / 3 - 8 * N ** 3 / 5,
    56 * N ** 3 / 15,
)


def utm_vers_latitude_longitude(x, y, fuseau, sud):
    xi = (y - (10000000.0 if sud else 0.0)) / (0.9996 * RAYON)
    eta = (x - 500000.0) / (0.9996 * RAYON)

    xi1, eta1 = xi, eta
    for rang, beta in enumerate(BETA, start=1):
        xi1 -= beta * math.sin(2 * rang * xi) * math.cosh(2 * rang * eta)
        eta1 -= beta * math.cos(2 * rang * xi) * math.sinh(2 * rang * eta)

    chi = math.asin(math.sin(xi1) / math.cosh(eta1))
    phi = chi
    for rang, delta in enumerate(DELTA, start=1):
        phi += delta * math.sin(2 * rang * chi)

    longitude = math.radians(fuseau * 6 - 183) + math.atan(math.sinh(eta1) / math.cos(xi1))
    return math.degrees(phi), math.degrees(longitude)


# ============================================================
# Projection utilisée par le flux, selon le département
# ============================================================

# Département d'outre-mer : fuseau UTM, hémisphère sud, puis l'emprise où la
# position calculée doit tomber (latitude mini et maxi, longitude mini et maxi).
OUTRE_MER = {
    "971": (20, False, 15.7, 18.2, -63.3, -60.9),
    "977": (20, False, 15.7, 18.2, -63.3, -60.9),
    "978": (20, False, 15.7, 18.2, -63.3, -60.9),
    "972": (20, False, 14.3, 15.0, -61.3, -60.7),
    "973": (22, False, 2.0, 6.0, -54.7, -51.5),
    "974": (40, True, -21.5, -20.8, 55.1, 55.9),
    "975": (21, False, 46.7, 47.2, -56.5, -56.0),
    "976": (38, True, -13.1, -12.5, 44.9, 45.4),
}


def departement_du_cog(cog_commune):
    cog = (cog_commune or "").strip().upper()
    return cog[:3] if cog[:2] in ("97", "98") else cog[:2]


def position_depuis_xy(x, y, departement):
    """Latitude et longitude en degrés, ou None quand la projection n'est pas sûre."""
    zone = OUTRE_MER.get(departement)

    if zone:
        latitude, longitude = utm_vers_latitude_longitude(x, y, zone[0], zone[1])
        if zone[2] <= latitude <= zone[3] and zone[4] <= longitude <= zone[5]:
            return latitude, longitude
        return None

    # Emprise du Lambert 93 : aucune projection d'outre-mer n'y donne de coordonnées.
    if departement[:2] in ("97", "98"):
        return None
    if 90000 < x < 1300000 and 6000000 < y < 7200000:
        return lambert93_vers_latitude_longitude(x, y)
    return None


def ecart_en_metres(latitude1, longitude1, latitude2, longitude2):
    a = (
        math.sin(math.radians(latitude2 - latitude1) / 2) ** 2
        + math.cos(math.radians(latitude1))
        * math.cos(math.radians(latitude2))
        * math.sin(math.radians(longitude2 - longitude1) / 2) ** 2
    )
    return 2 * 6371008.8 * math.asin(math.sqrt(a))


# ============================================================
# Lecture du flux Structures au fil de l'eau
# ============================================================

def lire_pmej(chemin):
    """Rend une à une les personnes morales du flux, sans charger le fichier en mémoire."""
    ouvrir = gzip.open if chemin.endswith(".gz") else open
    decodeur = json.JSONDecoder()
    debut_du_tableau = re.compile(r'"pmej"\s*:\s*\[')
    separateur = re.compile(r"[\s,]*")

    with ouvrir(chemin, "rt", encoding="utf-8") as flux:
        tampon = ""
        dans_le_tableau = False

        while True:
            morceau = flux.read(1 << 20)
            tampon += morceau

            if not dans_le_tableau:
                trouve = debut_du_tableau.search(tampon)
                if not trouve:
                    if not morceau:
                        return
                    tampon = tampon[-32:]
                    continue
                tampon = tampon[trouve.end():]
                dans_le_tableau = True

            position = 0
            while True:
                position = separateur.match(tampon, position).end()
                if tampon.startswith("]", position):
                    return
                try:
                    objet, position = decodeur.raw_decode(tampon, position)
                except json.JSONDecodeError:
                    # Objet coupé par la fin du morceau : il faut lire la suite.
                    break
                yield objet

            tampon = tampon[position:]
            if not morceau:
                return


# ============================================================
# Transformation
# ============================================================

COLONNES = [
    "niveau",
    "finess",
    "usage_adresse",
    "cog_commune",
    "coordonnee_x",
    "coordonnee_y",
    "latitude",
    "longitude",
    "origine",
]


def vide(valeur):
    return valeur is None or str(valeur).strip() == ""


def ligne_adresse(niveau, finess, adresse, bilan):
    geo = adresse.get("coordonneesGeographique") or {}
    x, y = geo.get("coordonneeX"), geo.get("coordonneeY")
    latitude, longitude = geo.get("directionLatitude"), geo.get("directionLongitude")
    a_xy = not vide(x) and not vide(y)
    a_position = not vide(latitude) and not vide(longitude)

    if not a_xy and not a_position:
        bilan["sans_coordonnees"] += 1
        return None

    calculee = None
    if a_xy:
        calculee = position_depuis_xy(float(x), float(y), departement_du_cog(adresse.get("cogCommune")))

    if a_position:
        origine = "flux"
        bilan["flux"] += 1
        if calculee:
            ecart = ecart_en_metres(float(latitude), float(longitude), calculee[0], calculee[1])
            bilan["controlees"] += 1
            bilan["ecart_maximal"] = max(bilan["ecart_maximal"], ecart)
    elif calculee:
        origine = "calcul"
        bilan["calcul"] += 1
        latitude, longitude = "%.6f" % calculee[0], "%.6f" % calculee[1]
    else:
        origine = ""
        bilan["non_calculees"] += 1

    return {
        "niveau": niveau,
        "finess": finess,
        "usage_adresse": adresse.get("usageAdresse"),
        "cog_commune": adresse.get("cogCommune"),
        "coordonnee_x": x,
        "coordonnee_y": y,
        "latitude": latitude,
        "longitude": longitude,
        "origine": origine,
    }


def transformer_flux_en_table(chemin, bilan):
    for pmej in lire_pmej(chemin):
        finess_pmej = (pmej.get("informationsGeneralesPMEJ") or {}).get("numFinessPm")
        for adresse in pmej.get("adresse") or []:
            ligne = ligne_adresse("PMEJ", finess_pmej, adresse, bilan)
            if ligne:
                yield ligne

        for ege in pmej.get("ege") or []:
            finess_ege = (ege.get("informationsGeneralesEGE") or {}).get("numFinessEge")
            for adresse in ege.get("adresse") or []:
                ligne = ligne_adresse("EGE", finess_ege, adresse, bilan)
                if ligne:
                    yield ligne


# ============================================================
# Programme principal
# ============================================================

if __name__ == "__main__":

    entree = sys.argv[1] if len(sys.argv) > 1 else "input.json"
    sortie = sys.argv[2] if len(sys.argv) > 2 else "coordonnees.csv"

    bilan = {
        "flux": 0,
        "calcul": 0,
        "non_calculees": 0,
        "sans_coordonnees": 0,
        "controlees": 0,
        "ecart_maximal": 0.0,
    }

    with open(sortie, "w", newline="", encoding="utf-8") as fichier:
        table = csv.DictWriter(fichier, fieldnames=COLONNES)
        table.writeheader()
        for ligne in transformer_flux_en_table(entree, bilan):
            table.writerow(ligne)

    print("Adresses avec latitude et longitude données par le flux :", bilan["flux"])
    print("Adresses dont la latitude et la longitude sont calculées depuis x et y :", bilan["calcul"])
    print("Adresses avec x et y mais sans projection sûre (non calculées) :", bilan["non_calculees"])
    print("Adresses sans coordonnées :", bilan["sans_coordonnees"])
    print(
        "Contrôle : sur les %d adresses qui portent x, y, latitude et longitude, "
        "écart maximal entre la position du flux et la position calculée : %.2f m"
        % (bilan["controlees"], bilan["ecart_maximal"])
    )
    print("Résultat écrit dans", sortie)

from .connexion       import get_finess_connection, get_duckdb_connection
from .pretraitement    import (
    normaliser_texte, supprimer_stopwords, mapper_type_voie, extraire_dept,
    extraire_siren,
    pretraiter_denomination, pretraiter_type_voie, pretraiter_libelle_voie,
    pretraiter_numero_voie, pretraiter_code_commune,
    pretraiter_eg, pretraiter_ej, pretraiter_etab, pretraiter_ul,
)
from .scoring          import (
    score_textuel, score_initiales,
    calc_score_nom, calc_score_adresse, calc_score_global,
)
from .matching         import est_valide, classifier_resultat
from .siretisation     import (
    choisir_nom_etab, scorer_paire_eg_etab, matching_direct_siret,
    scorer_paire_approfondi_eg,
)
from .sirenisation     import (
    choisir_nom_ul, scorer_paire_ej_ul, matching_direct_siren,
    construire_perimetre_abc,
    normaliser_ape, score_ape, score_date, scorer_paire_approfondi,
)
from .comparaison      import (
    charger_siretisation_depuis_phases, charger_sirenisation_depuis_phases,
    charger_et_fusionner_phases,
    construire_vue_a, synthese_par_ej, synthese_globale,
)
from .excel_export     import (
    LABELS, export_phase1_excel, export_topn_excel, export_comparaison_excel,
)
from .display          import afficher_tableau, afficher_synthese
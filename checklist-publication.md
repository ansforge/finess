# ✅ Checklist pré-publication du projet

Ce document recense les vérifications à effectuer avant la publication du code source sur une plateforme publique (ex : GitHub, code.gouv.fr).

---

## 📘 1. Juridique & Licences

- [ ] Tous les fichiers ont une licence clairement définie (MIT par défaut).
- [ ] Un fichier `LICENSE` est présent à la racine du dépôt.
- [ ] Les dépendances ont des licences compatibles et connues.
- [ ] Les éventuels composants modifiés (forks, librairies internes) sont identifiés et leur licence respectée.
Les mentions de licence sont intégrées dans les fichiers principaux ou selon les règles [reuse.software](https://reuse.software/).

---

## 🔐 2. Sécurité

- [ ] L’historique Git a été vérifié : aucune donnée sensible (clé, mot de passe, IP interne, etc.).
- [ ] Aucune donnée de production, ni jeux de données réels dans les scripts, exports ou exemples.
- [ ] Le code a été audité ou testé pour détecter d’éventuelles vulnérabilités.
- [ ] `.gitignore` est correctement configuré pour exclure les fichiers sensibles ou inutiles.

---

## 📚 3. Documentation

- [ ] Un fichier `README.md` présente le projet, son objectif et sa structure.
- [ ] Une documentation technique est disponible :  
  - [ ] Architecture du projet  
  - [ ] Description des flux (in/out)  
  - [ ] DDL (schéma de la base)  
  - [ ] Schémas JSON des flux
- [ ] Un guide `CONTRIBUTING.md` est présent pour les futurs contributeurs.
- [ ] Des instructions sont disponibles pour l’installation ou les tests (si applicables).

---

## 🧪 4. Qualité du code

- [ ] Le dépôt contient des tests unitaires (si le code est testable).
- [ ] Une configuration de CI est présente (ex : `.github/workflows`).
- [ ] Le code est lisible, commenté et structuré.
- [ ] Aucun code mort ou commentaire interne obsolète.

---

## 📦 5. Organisation du dépôt

- [ ] Arborescence claire : `webapp/`, `flux/`, `database/`, `schemas/`, `docs/`…
- [ ] Schémas JSON présents et valides.
- [ ] DDL propres, sans références internes ou sensibles.
- [ ] Tous les fichiers inutiles ou temporaires sont supprimés (`.DS_Store`, `tmp/`, etc.).

---

## 📢 6. Publication & communication

- [ ] Le dépôt passe en mode **public**.
- [ ] Le lien est communiqué aux partenaires ou dans l’espace prévu.
- [ ] Une issue "premier suivi" est créée pour remonter les questions ou contributions.


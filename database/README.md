# 📄 DDL - Schéma de base de données

Ce répertoire contient le script SQL principal pour générer le schéma de base de données **FINESS**.

## Contenu

- `finess-ddl.sql` : script unique contenant :
  - la création des tables
  - les clés primaires (PK), index, contraintes d’unicité et de vérification
  - les séquences et les commentaires

## SGBD compatible

- PostgreSQL xx

## Exécution

```bash
psql -f finess-ddl.sql

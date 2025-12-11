# 🤝 Contribuer au projet FINESS

Merci de votre intérêt pour ce projet ! Ce guide vous explique comment contribuer efficacement et dans le respect des bonnes pratiques.

---

## 🧭 Principes généraux

- Le projet est publié sous licence [MIT](./LICENSE).
- Toutes les contributions (code, documentation, corrections) sont les bienvenues.
- Merci de respecter les règles de sécurité, de qualité et de lisibilité du code.

---

## 🛠️ Comment contribuer

### 💻 Pour les utilisateurs familiers avec Git (terminal)

#### 1. Fork & clone

```bash
# Forkez le dépôt sur GitHub
git clone https://github.com/ansforge/finess.git
cd finess
```

#### 2. créer une branche

```bash
# Créer une branche
git checkout -b feature/nom-de-votre-contribution
```

#### 3. Développez

- Suivez la structure existante du code.
- Documentez vos fonctions si nécessaire.
- Vérifiez que vous ne publiez aucune donnée sensible.

#### 4. Testez

- Si possible, ajoutez des tests unitaires.
- Vérifiez que les tests existants passent correctement.

#### 5. Commitez proproment

```bash
# Commit
git add .
git commit -m "Ajout : nouvelle fonctionnalité X"
```

#### 6. Poussez votre branche et proposez une Pull Request

```bash
# Push & PR
git push origin feature/nom-de-votre-contribution
```

### 🌐 Pour les utilisateurs moins familiers avec Git (interface web)

GitHub permet de contribuer **sans ligne de commande**. Voici les étapes principales :

#### 1. Créer une Issue

1. Rendez-vous sur l’onglet [Issues](https://github.com/finess/issues) du dépôt.  
2. Cliquez sur **New issue**.  
   [Exemple bouton New Issue](./docs/images/new-issue.png)
3. Donnez un titre clair et décrivez votre suggestion ou bug.  
4. Ajoutez toutes les informations utiles : captures, contexte, étapes pour reproduire…  
5. Cliquez sur **Submit new issue**.  
   [Exemple Submit Issue](./docs/images/submit-issue.png)

#### 2. Créer une branche depuis GitHub

1. Allez sur la page principale du dépôt.  
2. Cliquez sur le menu déroulant **Branch: main**.  
   [Menu Branch](./docs/images/menu-branch.png)
3. Tapez un nom pour votre branche (ex. `feature/ajout-docs`) et appuyez sur **Enter** pour créer la branche.  
   [Créer une branche](./docs/images/create-branch.png)
4. Vous pouvez maintenant modifier les fichiers directement dans GitHub.  

#### 3. Modifier des fichiers et enregistrer vos changements

1. Ouvrez le fichier que vous souhaitez modifier.  
2. Cliquez sur l’icône du crayon ✏️ pour éditer le fichier.  
   [Icône crayon pour éditer](./docs/images/edit-file.png)
3. Faites vos modifications.  
4. En bas de la page, remplissez le champ **Commit changes** :  
   - Choisissez **Commit directly to the branch**.  
   - Ajoutez un message de commit clair et descriptif (ex. `Docs: ajout d’un exemple de contribution depuis le web`).  
5. Cliquez sur **Commit changes**.  
   [Commit changes](./docs/images/commit-changes.png)

#### 4. Créer une Pull Request (PR)

1. GitHub détecte automatiquement que votre branche a des changements par rapport à la branche principale.  
2. Cliquez sur **Compare & pull request**.  
   [Bouton Compare & PR](./docs/images/compare-pr.png)
3. Ajoutez un titre et une description pour expliquer **ce que fait votre PR et pourquoi**.  
4. Sélectionnez le type de changement : nouvelle fonctionnalité, correction de bug, documentation, etc.  
5. Cliquez sur **Create pull request**.  
   [Créer PR](./docs/images/create-pr.png)

> ✅ Astuce : Même depuis le web, suivez les mêmes conventions de nommage de branches et de commits que pour la ligne de commande pour plus de clarté.



---

## 📝 Règles de nommage

### Branches

| Type       | Usage                                  | Exemple de nom de branche                    |
|------------|---------------------------------------|----------------------------------------------|
| feature/   | Nouvelle fonctionnalité                | `feature/ajout-authentification`             |
| fix/       | Correction de bug                     | `fix/correction-typo-accueil`                 |
| docs/      | Mise à jour ou ajout de documentation | `docs/mise-a-jour-readme`                      |
| refactor/  | Refactorisation sans modification fonctionnelle | `refactor/nettoyage-composants`               |
| test/      | Ajout ou correction de tests          | `test/ajout-tests-api`                         |

**Conseils :**  
- Utilisez des mots clairs et séparés par des tirets `-`  
- Soyez concis mais explicite sur l’objet de la branche  

---

### Commits

Les messages de commit doivent commencer par un mot-clé clair, suivi de deux-points, puis une description concise.

| Mot-clé      | Usage                                | Exemple de message de commit                        |
|--------------|------------------------------------|----------------------------------------------------|
| Ajout:       | Nouvelle fonctionnalité             | `Ajout : prise en charge du nouvel endpoint API`   |
| Correction:  | Correction de bug                  | `Correction : gestion du bug d’authentification`   |
| MAJ:         | Mise à jour / amélioration          | `MAJ : amélioration des performances du module X`  |
| Suppression: | Suppression de code ou fichiers    | `Suppression : retrait du script obsolète`         |
| Docs:        | Modification de documentation      | `Docs : mise à jour du guide de contribution`      |

**Bonnes pratiques :**  
- Commencez la description par une majuscule  
- Soyez précis et court (idéalement < 72 caractères)  
- Expliquez clairement ce que fait le commit

---

### Exemples complets

```bash
git commit -m "Ajout : gestion des erreurs dans la connexion API"
git commit -m "Correction : fix du crash lors de la saisie utilisateur"
git commit -m "MAJ : optimisation de la requête base de données"
git commit -m "Suppression : retrait des fichiers temporaires inutilisés"
git commit -m "Docs : ajout du chapitre sur la contribution dans README"
```

---

## 📝 Exemple de message pour Pull Request (PR)

### Titre de la PR

#### Description

Expliquez brièvement **ce que fait cette PR**, le problème qu’elle résout ou la fonctionnalité qu’elle ajoute.

#### Type de changement

- [ ] Nouvelle fonctionnalité
- [ ] Correction de bug
- [ ] Mise à jour de la documentation
- [ ] Refactorisation
- [ ] Autre (précisez) : ________

#### Checklist avant soumission

- [ ] Le code suit les règles de nommage et de style.
- [ ] Le code a été testé et fonctionne correctement.
- [ ] La documentation a été mise à jour si nécessaire.
- [ ] Aucune donnée sensible n’est incluse.
- [ ] Les commits sont clairs et cohérents.

#### Liens ou tickets associés

Indiquez ici les numéros de tickets ou liens liés à cette PR, si applicable.

---

## 🛠️ Comment remonter un bug ou proposer une amélioration

Pour signaler un problème ou suggérer une amélioration, utilisez l’onglet [Issues](https://github.com/finess/issues) du dépôt.

Merci de :
- Vérifier que le sujet n’a pas déjà été remonté
- Donner un titre clair
- Fournir un maximum d'informations :
  - Contexte
  - Etapes pour reproduire (pour un bug)
  - Comportement attendu
  - Captures d’écran ou extraits si utiles

---

Merci pour votre contribution ! 🙌

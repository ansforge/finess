# ❓ FAQ – FINESS

## 📌 Sommaire

- [Comment est alimenté FiNESS ?](#comment-est-alimenté-finess-)
- [Quel est l’impact de l’arrivée du nouveau FiNESS sur les flux ?](#quel-est-limpact-de-larrivée-du-nouveau-finess-sur-les-flux-)
- [Quel est le lien avec la nomenclature et comment détecter les évolutions ?](#quel-est-le-lien-avec-la-nomenclature-et-comment-détecter-les-évolutions-)

---

## Comment est alimenté FINESS ? <a id="comment-est-alimenté-finess-"></a>

Le référentiel FiNESS est alimenté par les **Gestionnaires des Autorités d’Enregistrement** via l’application FiNESS.  
Cela permet de saisir les autorisations et de décrire les différentes structures mobilisées dans les domaines :

- Sanitaire  
- Médico-social  
- Social
- Enseignement sanitaire  

Par ailleurs, des **flux de SI externes** permettent d’enrichir ces données :

- Le flux **PHARMA SI** alimente FiNESS avec les données des officines  
- Le flux **BIO2** alimente FiNESS avec les données des laboratoires  
- Le flux **ARHGOS / SI Autorisation** alimente FiNESS avec les données sanitaires  

Ces flux **rafraîchissent quotidiennement** les données FiNESS.

---

## Quel est l’impact de l’arrivée du nouveau FiNESS sur les flux ? <a id="quel-est-limpact-de-larrivée-du-nouveau-finess-sur-les-flux-"></a>

Les 3 flux entrants (**BIO2, PHARMA SI et ARHGOS / SI Autorisation**) restent d’actualité et sont consommés **à l’identique**.

Le flux sortant nommé **« flux standard »**, exposé sur sFTP pour les partenaires, est conservé et reproduit à l’identique, avec un **rafraîchissement quotidien**.  
Cependant, ce flux n’embarquant pas les nouvelles données, il est **voué à disparaître**. La date d’arrêt n’est pas encore définie.

Un **nouveau flux sortant**, exposé sur **data.gouv** au format **JSON**, sera mis en place pour exposer l’ensemble des données FiNESS (y compris les groupements).  
Ce nouveau flux sera **rafraîchi quotidiennement**.

Par ailleurs :
- Une version **historique mensuelle** sera exposée  
- Une version **historique annuelle** sera également mise à disposition  

Les anciens flux historiques sur data.gouv ne sont pas reproduits.  
Les fichiers ne seront plus rafraîchis après le déploiement du nouveau FiNESS.

---

## Quel est le lien avec la nomenclature et comment détecter les évolutions ? <a id="quel-est-le-lien-avec-la-nomenclature-et-comment-détecter-les-évolutions-"></a>

Le nouveau flux **data.gouv** fera référence dans sa description à l’ensemble des **nomenclatures NOS gérées par le SMT**.

L’**API du SMT** permet :
- de consommer les nomenclatures  
- d’être notifié des modifications  

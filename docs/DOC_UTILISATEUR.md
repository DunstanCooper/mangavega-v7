# MangaVega Tracker V7 — Guide Utilisateur

> **Audience** : Utilisateurs finaux, collectionneurs manga
> **Dernière révision** : 26 février 2026
> **Version** : 7.0.0

---

## Table des matières

1. [C'est quoi MangaVega Tracker ?](#1-cest-quoi-mangavega-tracker-)
2. [Comment ça marche](#2-comment-ça-marche)
3. [Le Viewer — Consulter votre collection](#3-le-viewer--consulter-votre-collection)
4. [Valider et rejeter des volumes](#4-valider-et-rejeter-des-volumes)
5. [L'onglet Pilotage local](#5-longlet-pilotage-local)
5bis. [L'onglet Suivi éditorial](#5bis-longlet-suivi-éditorial)
6. [Les emails de notification](#6-les-emails-de-notification)
7. [Ajouter ou supprimer une série](#7-ajouter-ou-supprimer-une-série)
8. [Le scan automatique](#8-le-scan-automatique)
9. [Sauvegarder vos données](#9-sauvegarder-vos-données)
10. [Questions fréquentes (FAQ)](#10-questions-fréquentes-faq)

---

## 1. C'est quoi MangaVega Tracker ?

MangaVega Tracker surveille automatiquement les sorties de mangas et light novels sur Amazon Japon. Il vous prévient par email quand un nouveau tome sort pour une série que vous suivez.

**Ce qu'il fait :**
- Scanne Amazon Japon quotidiennement pour 55 séries
- Détecte les nouveaux volumes papier (pas les ebooks)
- Filtre le bruit (artbooks, anthologies, coffrets, sponsorisés)
- Vous envoie un email récapitulatif avec les couvertures
- Maintient un historique complet de votre collection

**Ce qu'il ne fait pas :**
- Il n'achète rien automatiquement
- Il ne scanne pas les sites français (uniquement Amazon.co.jp)
- Il ne détecte pas les annonces de séries (seulement les volumes déjà listés sur Amazon)

---

## 2. Comment ça marche

```
Chaque jour, le tracker :

1. 📋 Lit la liste des 55 séries à suivre
2. 🔍 Cherche chaque série sur Amazon Japon
3. 📦 Identifie les volumes papier
4. 🆕 Compare avec ce qu'il connaît déjà
5. 📧 Vous envoie un email si nouveautés
6. 💾 Met à jour la base de données
7. 🌐 Publie la collection sur le viewer web
```

Tout est automatique. Vous n'avez rien à faire sauf consulter le viewer et traiter les volumes détectés.

---

## 3. Le Viewer — Consulter votre collection

### Accès

**En ligne (lecture seule)** :
https://dunstancooper.github.io/mangavega-v7/manga_collection_viewer.html

**En local (lecture + pilotage)** :
http://localhost:5000 (nécessite que le serveur tourne, voir §5)

### Onglets

| Onglet | Contenu |
|--------|---------|
| **Volumes** | Liste de tous les volumes détectés avec filtres |
| **Séries** | Vue par série avec nombre de tomes |
| **Prédictions** | Estimation des prochaines sorties |
| **Récapitulatif** | Statistiques globales |
| **📑 Suivi** | Workflow éditorial par volume (droits → contrats → facture) |
| **⚡ Pilotage** | Commandes pour le serveur local (mode admin) |

### Filtres disponibles

- **Recherche** : par titre ou ASIN
- **Éditeur** : filtrer par éditeur (Kadokawa, Shueisha, etc.)
- **Année** : filtrer par année de sortie
- **Statut** : Tous / À traiter / Validés / Rejetés
- **Série** : filtrer par série spécifique

### Mode Admin

Cliquez sur **Connexion** en haut à droite et entrez votre mot de passe. Le mode admin débloque :
- La validation/rejet des volumes
- La synchronisation avec GitHub
- L'onglet Pilotage local
- L'onglet Suivi éditorial

---

## 4. Valider et rejeter des volumes

Le tracker détecte parfois des produits qui ne sont pas des vrais tomes de la série (artbooks, novelisations, produits d'un homonyme). C'est normal — il vaut mieux attraper trop que pas assez.

### Pourquoi valider/rejeter ?

- **Valider** = "oui, c'est bien un vrai tome de cette série"
- **Rejeter** = "non, c'est un faux positif"

Les volumes validés apparaissent en vert, les rejetés en rouge, les non traités en gris.

### Comment faire

1. Ouvrez le viewer en mode admin
2. Parcourez les volumes avec le statut **À traiter**
3. Cliquez sur le bouton vert ✓ pour valider ou rouge ✗ pour rejeter
4. Un compteur de modifications apparaît en haut
5. Cliquez **☁️ Synchroniser avec GitHub** pour sauvegarder vos choix

Vos corrections seront appliquées au prochain scan.

### Corriger un numéro de tome

Si le tracker s'est trompé de numéro (ex: affiche "N/A" au lieu de "Tome 3"), cliquez sur le badge du tome pour le modifier manuellement.

---

## 5. L'onglet Pilotage local

Cet onglet permet de commander le tracker depuis le viewer, sans ouvrir de console.

### Prérequis

Le serveur local doit tourner. Double-cliquez sur `mangavega_server.bat` dans le dossier du projet. L'indicateur passe au vert quand le serveur est connecté.

### Les 3 boutons

| Bouton | Action | Durée |
|--------|--------|-------|
| **🔄 Synchroniser BDD** | Applique vos corrections (validations/rejets) à la base de données immédiatement | 2 secondes |
| **▶️ Lancer le scan** | Lance un scan de toutes les séries (ou d'une seule) | ~45 minutes (complet) |
| **💾 Backup BDD** | Crée une copie de sauvegarde de la base de données | Instantané |

### Options du scan

- **Champ série** : laissez vide pour scanner toutes les séries, ou tapez un nom pour scanner une seule série
- **--no-email** : coché par défaut, décochez pour recevoir le mail
- **--no-push** : cochez pour ne pas publier le JSON sur GitHub

### Le log en direct

Pendant un scan, le log défile en bas de la page pour montrer la progression en temps réel.

---

## 5bis. L'onglet Suivi éditorial

Cet onglet permet de suivre le workflow éditorial pour chaque nouveau tome détecté.
Pour chaque volume, 6 étapes séquentielles sont à valider :

| Étape | Description | Délai max |
|-------|-------------|-----------|
| **Mail NWK** | Demande d'offre envoyée à l'éditeur JP via NWK | 10 jours |
| **Draft AD** | Réception du draft des Ayants Droits | 10 jours |
| **Réponse NWK** | Réponse NWK (ok/non) sur le draft | 10 jours |
| **Contrat AD** | Réception du contrat à signer | 10 jours |
| **Signature NWK** | NWK signe et archive le contrat | 10 jours |
| **Facture** | Réception et paiement de la facture | 10 jours |

### Comment utiliser le suivi

1. Ouvrez le viewer en mode admin
2. Allez dans l'onglet **📑 Suivi**
3. Les volumes actifs apparaissent avec leur étape courante et le nombre de jours écoulés
4. Quand une étape est terminée, cliquez **✓ Fait** et entrez la date de complétion
5. Cliquez **☁️ Synchroniser** pour sauvegarder dans GitHub

### Code couleur

- **Rouge** : plus de 10 jours — relance automatique envoyée
- **Orange** : 7 à 10 jours — à surveiller
- **Vert** : moins de 7 jours — dans les délais
- **Bleu** : en pause (délai suspendu)

### Boutons disponibles

- **✓ Fait** : marque l'étape comme terminée (demande la date)
- **⏸ Pause** : suspend le délai jusqu'à une date (ex: attente réponse en vacances)
- **📨 Relancé** : réinitialise le délai de 10j (j'ai relancé manuellement)

### Déclenchement automatique

Un workflow est créé automatiquement pour chaque nouveau tome détecté lors du scan. Il part toujours de l'étape "Mail NWK".

---

## 6. Les emails de notification

Le tracker envoie trois types d'emails :

### Email de rapport (à chaque scan)

Un récapitulatif avec :
- Nombre de séries scannées
- Nombre de volumes trouvés
- Nombre de nouveautés
- Nombre de volumes à traiter
- Durée du scan

### Email de nouveautés (quand il y en a)

Un email détaillé avec pour chaque nouveau volume :
- Couverture
- Nom de la série (JP + FR)
- Numéro de tome
- Date de sortie
- Éditeur
- Lien vers Amazon

### Email workflow éditorial (quand des étapes sont à traiter)

Un brouillon est déposé dans votre boîte mail pro (Microsoft 365) pour chaque cycle de workflow. Il regroupe :
- Les nouvelles demandes d'offres (volumes fraîchement sortis)
- Les relances (étapes dépassant 10 jours sans réponse)

Le format est un email plain-text professionnel, groupé par éditeur japonais :

```
Bonjour Nicolas,

Il faudrait faire les offres pour :

Kadokawa Sneaker Bunko :
- Solo Leveling (LN) T13, sortie le 26/02/2026 — il vient de sortir et s'ajoute à la liste
- Re:Zero (LN) T22, sortie le 15/01/2026 — je t'avais fait un mail sur ce tome le 16/01/2026

Merci,
Eloi
```

**Note** : ces emails sont des brouillons à valider avant envoi. Ils apparaissent dans votre dossier "Brouillons" Outlook. Si le dépôt IMAP échoue, le fichier est sauvegardé dans le dossier `brouillons/` du projet (format .eml, ouvrable avec Outlook).

---

## 7. Ajouter ou supprimer une série

### Ajouter une série

Ouvrez le fichier `mangas_liste.json` avec un éditeur de texte et ajoutez une entrée :

```json
{
  "nom": "新しい漫画 [MANGA]",
  "nom_fr": "Nouveau Manga",
  "url": "https://www.amazon.co.jp/dp/XXXXXXXXXX"
}
```

**Règles :**
- Le `nom` doit se terminer par `[MANGA]` ou `[LN]`
- L'`url` doit être un lien vers un volume existant de la série sur Amazon.co.jp
- Le `nom_fr` est optionnel (le tracker le cherchera automatiquement)

### Supprimer une série

Supprimez l'entrée correspondante dans `mangas_liste.json`.

### Via le viewer (mode admin)

Vous pouvez aussi ajouter/supprimer des séries depuis l'onglet Séries du viewer. Les modifications sont sauvegardées dans le Gist et appliquées au prochain scan.

---

## 8. Le scan automatique

Le scan est programmé pour tourner automatiquement via le Planificateur de tâches Windows.

### Vérifier que ça tourne

1. Ouvrez le Planificateur de tâches (cherchez "Planificateur" dans le menu Windows)
2. Trouvez la tâche "MangaVega"
3. Vérifiez la date de dernière exécution

### Si le scan ne se lance pas

- Le PC doit être allumé et l'utilisateur connecté
- Si le PC est en veille, cochez "Réveiller l'ordinateur" dans les conditions
- Vérifiez que `mangavega_scheduled.bat` est bien configuré dans l'action

### Lancer un scan manuellement

Trois options :
1. **Depuis le viewer** : onglet ⚡ Pilotage → Lancer le scan
2. **Double-clic** sur `mangavega_scan.bat`
3. **Console** : `python app.py`

---

## 9. Sauvegarder vos données

### Sauvegarde automatique

Utilisez le bouton **💾 Backup BDD** dans le viewer. Les sauvegardes sont stockées dans le dossier `backups/` avec un horodatage. Les 10 dernières sont conservées.

### Sauvegarde manuelle

Copiez le fichier `manga_alerts.db` dans un endroit sûr. C'est le seul fichier qui contient vos données irremplaçables (historique des volumes, traductions, corrections).

### Restaurer une sauvegarde

Remplacez `manga_alerts.db` par une copie de sauvegarde. Le tracker reprendra avec les données de cette sauvegarde.

---

## 10. Questions fréquentes (FAQ)

### Pourquoi certains volumes affichent "N/A" comme numéro de tome ?

Les light novels (LN) n'ont souvent pas de numéro de tome dans leur titre Amazon. C'est normal pour les séries marquées `[LN]`. Pour les mangas, c'est plus rare — vous pouvez corriger le numéro manuellement dans le viewer.

### Pourquoi le scan dure 45 minutes ?

Le tracker fait ~300 requêtes HTTP vers Amazon avec des pauses entre chaque série pour éviter d'être bloqué. C'est le prix de la discrétion.

### J'ai rejeté un volume par erreur, comment revenir en arrière ?

Dans le viewer en mode admin, retrouvez le volume et changez son statut. Puis synchronisez.

### Le mail dit "332 À traiter" mais le viewer dit "1 À traiter"

C'est un bug connu quand le `GIST_ID` du script ne correspond pas à celui du viewer. Vérifiez que `config.py` pointe vers le bon Gist.

### Le scan tourne la nuit et dure 9 heures

Le PC est probablement passé en veille pendant le scan. Le script reprend quand le PC se réveille. Configurez le planificateur pour réveiller le PC ou programmez le scan quand vous utilisez le PC.

### Comment voir les logs ?

Trois options :
1. **Viewer** : onglet ⚡ Pilotage → Log en direct
2. **Fichier** : ouvrez `manga_tracker.log` avec un éditeur de texte
3. **Console** : les logs s'affichent en temps réel pendant l'exécution

### Le serveur local est "hors ligne" dans le viewer

Le serveur Flask n'est pas lancé. Double-cliquez sur `mangavega_server.bat` ou lancez `python api_server.py` dans une console. La lecture de la collection fonctionne toujours sans le serveur — seul le pilotage (scan, sync, backup) le nécessite.

### Puis-je utiliser le viewer depuis mon téléphone ?

Oui, la consultation fonctionne partout via GitHub Pages. Le pilotage (boutons scan/sync/backup) ne fonctionne que si le serveur tourne sur votre PC et que votre téléphone est sur le même réseau (localhost ne marche pas depuis un autre appareil).

### Comment créer un workflow pour un volume déjà dans la collection (avant la date de mise en place) ?

Dans l'onglet Volumes, trouvez le volume et cliquez sur le bouton **📑 Créer workflow** (mode admin). Le workflow démarrera à l'étape Mail NWK.

### Je ne reçois pas les brouillons workflow dans ma boite Outlook

Vérifiez que `IMAP_MOT_DE_PASSE` est renseigné dans le fichier `.env`. S'il est vide, les brouillons sont sauvegardés localement dans le dossier `brouillons/` (fichiers .eml).

---

> **Changelog documentation**
> - 2026-02-22 : Création initiale
> - 2026-02-26 : Ajout onglet Suivi éditorial, emails workflow

# Hưng Phát Accounting Suite

<samp>[Tiếng Việt](README.md) · [English](README.en.md) · [中文](README.zh.md) · **Français**</samp>

Application de comptabilité de bureau pour les entreprises vietnamiennes, développée avec
**Python + PySide6**. Elle prend en charge les régimes comptables de la **Circulaire 200**
et de la **Circulaire 133** (commutables) et stocke tout localement dans **SQLite** —
aucun serveur requis, tout s'exécute sur la machine de l'utilisateur.

> Nom affiché dans l'application : *Hung Phat Accounting* — organisation : *Hung Phat M&E*.

---

## Fonctionnalités principales

| Module | Description |
|---|---|
| **Tableau de bord** | Vue d'ensemble : produits/charges, créances/dettes, graphiques de tendance, indicateurs rapides. |
| **Journal général** | Saisie manuelle d'écritures avec marquage du tiers par ligne (comptes 131/331). |
| **Répertoire** | Plan comptable, clients/fournisseurs, articles, entrepôts. |
| **Ventes / Achats** | Factures de vente/d'achat générant automatiquement écritures et mouvements de stock. |
| **Trésorerie** | Bons de recette/dépense en espèces et en banque, avec choix du tiers pour les créances/dettes. |
| **Stock** | Fiches entrées–sorties–stock des matières et **calcul du coût de revient** (réparti au prorata des matières). |
| **Immobilisations** | Registre des immobilisations et amortissements. |
| **Fiscalité** | Déclarations de TVA / d'impôt sur les sociétés, préremplies avec les informations de la société. |
| **États** | Grand livre, grands livres détaillés, balance, compte de résultat ; export Excel/PDF. |
| **Factures électroniques** | Récupération des factures par e-mail (IMAP), analyse du XML en documents brouillons. |
| **Clôture de fin d'année** | Verrouille les données d'un exercice ; clôture automatique 48 h après la fin d'année si rien n'est fait. |

### Récupération des factures électroniques par e-mail

- Se connecte à la boîte mail via **IMAP** avec deux modes d'authentification :
  **OAuth2 (XOAUTH2)** pour Gmail, ou **mot de passe d'application / mot de passe IMAP**
  (Yahoo, IMAP personnalisé).
- Analyse le **XML de facture électronique au standard TT78/Décret 123** (balises `TTChung`,
  `NDHDon`, `NBan`, `NMua`, `DSHHDVu`…), compatible avec la plupart des fournisseurs
  (Viettel, VNPT, MISA, BKAV…).
- Lit aussi le **XML compressé dans un `.zip`** ; tout PDF joint est conservé pour référence.
- **Classification automatique vente/achat selon le code fiscal de la société** : si le code
  fiscal du vendeur correspond à la société → facture de **vente** (tiers = acheteur) ;
  sinon → facture d'**achat**.
  - Les factures d'**achat** arrivent généralement dans `INBOX` (le portail e-facture vous les envoie).
  - Les factures de **vente** que vous composez et envoyez aux clients se trouvent dans `[Gmail]/Sent Mail`.
- Le bouton **« Rescanner depuis le début »** réinitialise le repère UID pour re-parcourir
  tout le dossier (les doublons sont évités par le numéro de facture).

Des instructions détaillées sont disponibles dans l'application :
**Guide d'utilisation → « Récupérer automatiquement les factures électroniques (HĐĐT) par e-mail »**.

---

## Prérequis

- **Python ≥ 3.11**
- Windows (testé sous Windows 11) ; devrait aussi fonctionner sur toute plateforme prise en charge par PySide6.

## Installation & lancement

```bash
# 1) Créer un environnement virtuel
python -m venv .venv
# Windows :
.venv\Scripts\activate
# macOS/Linux :
# source .venv/bin/activate

# 2) Installer les dépendances (avec les extras d'export d'états)
pip install -e ".[reports]"

# 3) Lancer l'application
python main.py
```

Pour installer aussi les outils de test : `pip install -e ".[dev,reports]"`.

### Données utilisateur

La base de données et les pièces jointes sont stockées hors de l'arborescence source :

```
%APPDATA%\HungPhatAccounting\
├── ketoan.db          # toutes les données comptables (SQLite)
└── einvoices\         # PDF de factures téléchargés depuis l'e-mail
```

Au premier lancement, l'application crée la base de données et initialise le plan comptable.

### Données de démonstration & réinitialisation

Dans **Paramètres → Données de démonstration** :
- **Charger les données de démo** — génère une année complète de chiffres pour tester.
- **Effacer toutes les données** — pour commencer à saisir des données réelles (conserve
  toujours le plan comptable et la circulaire sélectionnée).

---

## Structure du projet

```
Ketoan/
├── main.py                  # Point d'entrée (QApplication + ChromeWindow)
├── app/                     # Config, thème, poller e-mail, raccourcis
├── domain/                  # Logique métier en pur Python (indépendante de l'UI)
│   ├── models/              #   Dataclasses : Invoice, Journal, Partner, Item…
│   └── services/            #   Logique : ventes/achats, stock, coût, fiscalité, e-facture…
├── data/                    # Couche de données
│   ├── database.py          #   Connexion SQLite partagée
│   ├── migrations/          #   *.sql créant/mettant à jour le schéma dans l'ordre
│   ├── repositories/        #   Requêtes par table
│   └── email/               #   Client IMAP + OAuth (récupération des e-factures)
├── ui/                      # Interface PySide6
│   ├── chrome/              #   Coquille de fenêtre, barre latérale, barre d'état
│   ├── screens/             #   Un écran par module
│   ├── modals/ primitives/  #   Boîtes de dialogue & composants réutilisables
│   └── resources/           #   QSS, polices, icônes
├── reports/exporters/       # Export Excel (openpyxl) / PDF (reportlab)
└── tests/                   # pytest (domain, data, reports, ui)
```

### Architecture

Un découpage en couches clair : **UI → services domaine → dépôts → SQLite**. La couche
`domain` n'importe pas PySide6, elle peut donc être testée indépendamment sans interface
graphique. Tout le travail SQLite passe par une connexion partagée unique sur le thread
principal ; les tâches réseau (IMAP) s'exécutent dans un `QThread` puis renvoient les
résultats au thread principal pour une écriture en base sûre.

---

## Base de données

Le schéma est géré par les fichiers de `data/migrations/` (nommés `NNN_nom.sql`), exécutés
dans l'ordre au démarrage. Pour modifier le schéma, créez un nouveau fichier de migration
avec le numéro suivant — ne modifiez pas les fichiers déjà publiés.

## Tests

```bash
python -m pytest --basetemp=.pytest_tmp
```

> ⚠️ Sous Windows, l'option `--basetemp=.pytest_tmp` est requise, sinon les tests utilisant
> un dossier temporaire échouent avec des erreurs de permission.

Les tests portent surtout sur les couches `domain`/`data` (sans GUI). Exemples liés aux
e-factures : `tests/domain/test_einvoice_parser.py`, `tests/domain/test_invoice_import_service.py`,
`tests/domain/test_email_config_service.py`, `tests/data/test_imap_client.py`.

---

## Notes de développement

- **Dépendances d'exécution** : `PySide6`, `google-auth`, `google-auth-oauthlib`
  (voir `pyproject.toml`). Groupes optionnels : `reports` (openpyxl, reportlab),
  `dev` (pytest, pytest-qt).
- **Modèle de comptabilisation** : le verrouillage se fait par **clôture de fin d'année**
  plutôt que par document.
- **Sécurité locale** : les mots de passe/jetons OAuth sont seulement *obscurcis* en base64
  dans la table `settings` — c'est une machine personnelle, pas une véritable frontière de
  sécurité (un trousseau système est hors périmètre pour l'instant).

# FABOuanes FastAPI

FABOuanes est maintenant expose par une entree **FastAPI** tout en preservant:

- les templates et le rendu UI existants,
- les workflows metier,
- la base SQLite/PostgreSQL existante,
- la compatibilite mobile `/api/v1`,
- le packaging desktop Windows.

La migration FastAPI est maintenant la source principale:

- `app/` contient la plateforme, le metier et la persistence,
- l'ancien paquet Flask `fabouanes/` a ete retire,
- les proxys de transition ont ete remplaces par des routes FastAPI natives.

## Structure principale

```text
app/
  main.py
  core/
  api/
  web/
  services/
  repositories/
  utils/
templates/
static/
tests/
launcher/
installer/windows/
alembic/
```

## Prerequis

- Python 3.11+
- Windows 10/11 pour le packaging desktop
- Inno Setup 6 pour produire l'installateur

## Installation locale

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Configuration

Copier `.env.example` en `.env` si besoin, puis ajuster:

- `SECRET_KEY`
- `DATABASE_URL` pour PostgreSQL local
- `FAB_HOST`
- `FAB_PORT`
- `DEFAULT_ADMIN_USERNAME`
- `DEFAULT_ADMIN_PASSWORD`

La configuration par defaut utilise PostgreSQL local:

```env
DATABASE_URL=postgresql://postgres:0000@127.0.0.1:5432/fabouanes
```

Si `DATABASE_URL` est absent, l'application utilise aussi ce PostgreSQL local par defaut. SQLite reste reserve au fallback explicite:

```env
FAB_DATABASE_ENGINE=sqlite
```

ou avec une URL SQLite complete:

```env
DATABASE_URL=sqlite:///C:/Users/you/AppData/Local/FABOuanes/database.db
```

## Lancer le serveur FastAPI

### Developpement

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 5000 --reload
```

### Serveur simple

```powershell
python -m launcher.run_server
```

Le serveur ecoute par defaut sur `0.0.0.0:5000` pour le mode reseau.

Depuis Windows, `LANCER.bat` lance aussi ce mode serveur reseau par defaut. La commande equivalente est:

```powershell
python launcher.py --server
```

## Lancer le client desktop

```powershell
python launcher.py
```

Le lanceur:

- prepare les dossiers runtime,
- initialise/migre la base PostgreSQL par defaut,
- demarre Uvicorn en mode reseau,
- ouvre l'UI dans WebView,
- conserve la compatibilite avec le QR mobile.

Le client desktop reste disponible avec `python launcher.py`; il ouvre la WebView locale mais garde l'acces reseau actif.

## Espace bons

Le menu `Outils > Espace bons` remplace l'ancien lecteur PDF. Il permet de chercher et lire:

- les bons d'achat,
- les bons de vente,
- les bons de versement et d'avance,
- les bons de production,
- les historiques client,
- les PDF externes importes manuellement.

## Tests

La nouvelle base de tests utilise `pytest`.

```powershell
python -m pytest
```

Par defaut, les tests utilisent SQLite dans `tests/_runtime_fastapi`.
Pour lancer les tests avec un cluster PostgreSQL local, definir `FAB_TEST_DB=postgres`.

Les tests FastAPI sont organises par domaine:

- `tests/web/`
- `tests/api/`
- `tests/services/`
- `tests/printing/`

## Push GitHub

Depuis la racine, le script `PUSH_GITHUB.bat` ajoute les changements, cree un commit, fait un `pull --rebase`, puis pousse la branche courante vers `origin`.

## Base de donnees et migrations

La migration preserve le schema existant.

- bootstrap schema: `app.core.schema.init_db()`
- moteur SQLAlchemy Core: `app/core/database.py`
- revisionning: `alembic/`

Au demarrage:

1. les dossiers runtime sont assures,
2. la base locale est copiee si necessaire,
3. le schema applicatif est bootstrappe,
4. Alembic fait `stamp` puis `upgrade`.

## Packaging Windows

### Construire l'EXE

```powershell
installer\windows\COMPILER_EXE_AVEC_TESTS.bat
```

### Construire l'installateur

```powershell
installer\windows\BUILD_INSTALLATEUR_DESKTOP.bat
```

Raccourci depuis la racine:

```powershell
CREER_INSTALLATEUR_WINDOWS.bat
```

Artefacts attendus:

- `dist\FABOuanes\FABOuanes.exe`
- `installer_output\FABOuanes_Setup.exe`

Les scripts sous `deploy\windows\` sont de simples wrappers de compatibilite vers `installer\windows\`.

## Points de transition importants

- `app/main.py` est maintenant l'entree ASGI principale.
- `app.py` et `wsgi.py` sont des shims de compatibilite.
- `app/core/`, `app/services/` et `app/repositories/` portent maintenant la logique auparavant dupliquee.
- le montage WSGI global Flask et les proxys de transition ont ete retires.

## Fichiers utiles

- `app/main.py`
- `app/web/`
- `app/api/v1/`
- `app/core/database.py`
- `launcher.py`
- `launcher/run_server.py`
- `installer/windows/FABOuanes_Setup.iss`
- `MIGRATION_REPORT.md`

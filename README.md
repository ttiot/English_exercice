# English Explorer

Application web Flask pour proposer des exercices d'anglais adaptés à un élève de 6ème.

## Fonctionnalités

- Création de profils élèves sans authentification.
- Sessions d'entraînement configurables (nombre de questions, durée facultative).
- Génération d'exercices variés (nombres, vocabulaire, traductions) et priorité aux exercices préparés par les parents.
- Correction globale en fin de session et historique des réponses.
- Tableau de bord élève avec suivi de progression par catégorie.
- Espace parents protégé par mot de passe pour suivre les progrès et préparer des exercices personnalisés.

## Démarrage local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export FLASK_APP=wsgi.py
flask run --debug
```

La base SQLite est créée automatiquement dans `instance/app.db`.

## Variables d'environnement utiles

- `SECRET_KEY` : clé secrète Flask.
- `PARENT_PORTAL_PASSWORD` : mot de passe de l'espace parents (défaut `parents123`).
- `DATABASE_URL` : URL de la base de données (défaut SQLite).

## Utilisation de Docker

Construire l'image :

```bash
docker build -t english-explorer .
```

Lancer le conteneur :

```bash
docker run -p 5000:5000 --env SECRET_KEY=change-me english-explorer
```

## Tests

Aucun test automatisé n'est fourni pour cette première version. Lancez une session depuis l'interface pour vérifier le fonctionnement.

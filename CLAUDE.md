# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Flask web app ("English Explorer") that gives English exercises to French middle-school students (6ème/5ème). User-facing strings, flash messages, and most comments are in **French** — keep that convention when adding new text. Deeper architecture and conventions live in [`agents.MD`](./agents.MD); read it before non-trivial work.

## Commands

```bash
# Local dev
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export FLASK_APP=wsgi.py FLASK_ENV=development
flask run --debug                       # http://127.0.0.1:5000

# Smoke-test DB connection / config
python test_db_connection.py

# Docker (production-shaped run, with Caddy + backup sidecar)
docker-compose up --build
docker-compose logs -f app
docker-compose exec app sh

# Inspect the SQLite store
sqlite3 instance/app.db                 # local dev
sqlite3 /data/app.db                    # inside the container / volume
```

There is **no automated test suite** (`README.md` is explicit about this). Don't claim tests pass — manually exercise the affected route/template, or add a `pytest` setup if asked.

## Required environment variables

`FLASK_ENV=development` enables defaults (dev `SECRET_KEY`, `admin1234` admin password, ephemeral `FERNET_KEY`). In any other mode, `app/config.py` will **raise on import** unless these are set:

- `SECRET_KEY`
- `DEFAULT_ADMIN_PASSWORD`
- `FERNET_KEY` — base64 Fernet key (generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`). Used to encrypt the OpenAI API key stored in `openai_config.api_key_encrypted`. **Never rotate without re-saving the key via the admin UI** — the stored ciphertext becomes unreadable otherwise.

Optional: `DATABASE_URL` (default `sqlite:///<DATA_DIR>/app.db`), `DATA_DIR` (default `/data`), `UPLOAD_FOLDER`, `DEFAULT_ADMIN_EMAIL`, `OPENAI_API_KEY` / `OPENAI_MODEL` / `OPENAI_BASE_URL` (env fallbacks used only when no `OpenAIConfig` row is active in DB).

## Architecture (big picture)

- **Entry point**: `wsgi.py` → `app.create_app()` (factory pattern). Gunicorn runs `wsgi:app` in Docker.
- **App factory** (`app/__init__.py`) does a lot at startup, in order, under an `fcntl` file lock at `<DATA_DIR>/.init.lock`:
  1. `db.create_all()` — creates missing tables from SQLAlchemy models.
  2. `ensure_schema_migrations()` — **manual** `ALTER TABLE` statements for SQLite. There is no Alembic flow despite `Flask-Migrate` being installed; when you change a model, add the corresponding `ALTER` here so existing DBs upgrade in place.
  3. `ensure_default_categories()` / `ensure_default_badges()` / `ensure_default_prerequisites()` — seed reference data.
  4. `ensure_admin_account(...)` — bootstraps the admin from env vars.
  Also registers SQLite `PRAGMA` (WAL, foreign_keys=ON) on every connect, sets a strict CSP / security-headers `after_request`, and exposes `/health` for the Docker healthcheck.
- **One blueprint, one routes file**: `app/routes.py` (~2200 lines) holds *every* route — auth, students, sessions, parent dashboard, admin, exercise bank, imports. Search by URL prefix (`/students/`, `/parents/`, `/exercise-bank`, etc.) rather than by file. Authorization is enforced via three decorators defined in the same file: `@_login_required`, `@_parent_required`, `@_admin_required`. Use them — don't roll your own auth check.
- **Models** (`app/models.py`): `Student`, `PracticeSession`, `SessionExercise`, `PreparedExerciseSet`, `QuestionCategory`, `StudentSkillProgress`, `Badge` / `StudentBadge`, `WeeklyGoal`, `ReviewPlan`, `SkillPrerequisite`. Roles live on `Student.role` (`student` / `parent` / `admin`). See the relations diagram in `agents.MD`.
- **Exercise generation** (`app/exercise_factory.py`): procedural. New exercise types must (a) add a `_generate_xxx(difficulty) -> ExercisePrompt`, (b) register it in `GENERATOR_REGISTRY`, and (c) add the matching entry to `DEFAULT_CATEGORY_NAMES` / `DEFAULT_CATEGORY_METADATA` in `app/models.py` so it gets seeded. Difficulty levels: `beginner`, `intermediate`, `advanced`.
- **Validation / sanitization** (`app/validators.py`): use `validate_*` and `sanitize_text_input` for any user-supplied data. CSRF is global via `Flask-WTF` (`csrf.init_app(app)`); forms must include the `csrf_token` (already injected into the Jinja context).
- **Templates**: `app/templates/*.html`, all extend `base.html` (blocks: `title`, `content`, `scripts`). Static assets in `app/static/{css,js,img}/`; uploaded avatars go to `<UPLOAD_FOLDER>` (mounted volume in Docker, *not* `app/static/uploads`).

## Conventions worth respecting

- French for user-visible text (flash messages, page copy, error strings); English is fine for code identifiers.
- Private/internal helpers are prefixed `_` (e.g. `_login_required`, `_load_user_from_session`).
- Use `flash(msg, level)` with levels `success` / `info` / `warning` / `danger` to match existing template styling.
- Use `abort(403)` / `abort(404)` for authorization/not-found rather than custom redirects.
- Type hints on public functions; constants in `UPPER_CASE`.

## Deployment notes

- `Dockerfile` runs as non-root `appuser` (uid 10001), with `/data` as the persistence volume; the container is `read_only: true` in `docker-compose.yml` (only `/tmp` is writable tmpfs and `/data` is the named volume). Don't write outside `/data` at runtime.
- `docker-compose.yml` ships three services: Caddy reverse proxy (TLS for `english.michaux.name`), the Flask app, and a nightly Alpine `sqlite3 .backup` sidecar that prunes backups older than 14 days.
- CI (`.github/workflows/docker.yml`) builds & pushes multi-arch images to GHCR on `main` (tag `unstable` + `sha-<short>`) and on Git tags (semver tags + `latest`).

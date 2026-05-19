"""Migrations de schéma manuelles (SQLite, ALTER TABLE conditionnels).

L'application n'utilise pas Alembic malgré la présence de Flask-Migrate :
toutes les évolutions de schéma sont exprimées ici par des ALTER TABLE
idempotents, lancés depuis ``create_app()`` après ``db.create_all()``.

Lorsqu'une colonne est ajoutée à un modèle, ajouter le bloc correspondant
ici pour que les bases existantes se mettent à niveau au prochain démarrage.
"""

from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash

from ..extensions import db


def ensure_schema_migrations() -> None:
    inspector = inspect(db.engine)
    table_names = inspector.get_table_names()

    needs_commit = False

    if "students" in table_names:
        student_columns = {
            column["name"] for column in inspector.get_columns("students")
        }

        if "email" not in student_columns:
            db.session.execute(
                text("ALTER TABLE students ADD COLUMN email VARCHAR(255)")
            )
            needs_commit = True

        if "role" not in student_columns:
            db.session.execute(
                text("ALTER TABLE students ADD COLUMN role VARCHAR(20) DEFAULT 'student'")
            )
            db.session.execute(
                text(
                    "UPDATE students SET role = 'student' WHERE role IS NULL"
                )
            )
            needs_commit = True

        if "avatar_filename" not in student_columns:
            db.session.execute(
                text("ALTER TABLE students ADD COLUMN avatar_filename VARCHAR(255)")
            )
            needs_commit = True

        if "pin_hash" not in student_columns:
            default_hash = generate_password_hash("0000")
            db.session.execute(
                text("ALTER TABLE students ADD COLUMN pin_hash VARCHAR(255) DEFAULT :hash"),
                {"hash": default_hash}
            )
            db.session.execute(
                text("UPDATE students SET pin_hash = :hash WHERE pin_hash IS NULL"),
                {"hash": default_hash}
            )
            needs_commit = True

        if "target_cefr_level" not in student_columns:
            db.session.execute(
                text("ALTER TABLE students ADD COLUMN target_cefr_level VARCHAR(10)")
            )
            needs_commit = True

        if "target_grade" not in student_columns:
            db.session.execute(
                text("ALTER TABLE students ADD COLUMN target_grade VARCHAR(10)")
            )
            needs_commit = True

        if "target_trimester" not in student_columns:
            db.session.execute(
                text("ALTER TABLE students ADD COLUMN target_trimester INTEGER")
            )
            needs_commit = True

        if "interests" not in student_columns:
            db.session.execute(
                text("ALTER TABLE students ADD COLUMN interests TEXT")
            )
            needs_commit = True

        if "preferred_domains" not in student_columns:
            db.session.execute(
                text("ALTER TABLE students ADD COLUMN preferred_domains VARCHAR(255)")
            )
            needs_commit = True

        if "reset_token_hash" not in student_columns:
            db.session.execute(
                text("ALTER TABLE students ADD COLUMN reset_token_hash VARCHAR(255)")
            )
            needs_commit = True

        if "reset_token_expires_at" not in student_columns:
            db.session.execute(
                text("ALTER TABLE students ADD COLUMN reset_token_expires_at DATETIME")
            )
            needs_commit = True

    if "practice_sessions" in table_names:
        session_columns = {
            column["name"] for column in inspector.get_columns("practice_sessions")
        }

        if "time_limit_minutes" not in session_columns:
            db.session.execute(
                text("ALTER TABLE practice_sessions ADD COLUMN time_limit_minutes INTEGER")
            )
            needs_commit = True

        if "duration_seconds" not in session_columns:
            db.session.execute(
                text("ALTER TABLE practice_sessions ADD COLUMN duration_seconds INTEGER")
            )
            needs_commit = True

        if "time_limit_seconds" not in session_columns:
            db.session.execute(
                text("ALTER TABLE practice_sessions ADD COLUMN time_limit_seconds INTEGER")
            )
            needs_commit = True

        if "difficulty" not in session_columns:
            db.session.execute(
                text(
                    "ALTER TABLE practice_sessions ADD COLUMN difficulty VARCHAR(20) DEFAULT 'beginner'"
                )
            )
            db.session.execute(
                text(
                    "UPDATE practice_sessions SET difficulty = 'beginner' WHERE difficulty IS NULL"
                )
            )
            needs_commit = True

        if "session_type" not in session_columns:
            db.session.execute(
                text("ALTER TABLE practice_sessions ADD COLUMN session_type VARCHAR(20) DEFAULT 'practice'")
            )
            db.session.execute(
                text("UPDATE practice_sessions SET session_type = 'practice' WHERE session_type IS NULL")
            )
            needs_commit = True

        if "instructions_fr" not in session_columns:
            db.session.execute(
                text("ALTER TABLE practice_sessions ADD COLUMN instructions_fr TEXT")
            )
            needs_commit = True

        if "instructions_en" not in session_columns:
            db.session.execute(
                text("ALTER TABLE practice_sessions ADD COLUMN instructions_en TEXT")
            )
            needs_commit = True

    if "question_categories" in table_names:
        category_columns = {
            column["name"] for column in inspector.get_columns("question_categories")
        }

        if "domain" not in category_columns:
            db.session.execute(
                text("ALTER TABLE question_categories ADD COLUMN domain VARCHAR(50)")
            )
            needs_commit = True

    if "student_skill_progress" in table_names:
        progress_columns = {
            column["name"] for column in inspector.get_columns("student_skill_progress")
        }

        nullable_fixups = {
            "mastery": 0.0,
            "total_attempts": 0,
            "correct_attempts": 0,
            "correct_streak": 0,
        }
        for column_name, default_value in nullable_fixups.items():
            if column_name in progress_columns:
                db.session.execute(
                    text(
                        f"UPDATE student_skill_progress SET {column_name} = :value "
                        f"WHERE {column_name} IS NULL"
                    ),
                    {"value": default_value},
                )
                needs_commit = True

        if "cecrl_level" not in category_columns:
            db.session.execute(
                text("ALTER TABLE question_categories ADD COLUMN cecrl_level VARCHAR(10)")
            )
            needs_commit = True

        if "grade_level" not in category_columns:
            db.session.execute(
                text("ALTER TABLE question_categories ADD COLUMN grade_level VARCHAR(10)")
            )
            needs_commit = True

        if "trimester" not in category_columns:
            db.session.execute(
                text("ALTER TABLE question_categories ADD COLUMN trimester INTEGER")
            )
            needs_commit = True

        if "order_index" not in category_columns:
            db.session.execute(
                text("ALTER TABLE question_categories ADD COLUMN order_index INTEGER")
            )
            needs_commit = True

        if "unlocked_by_default" not in category_columns:
            db.session.execute(
                text("ALTER TABLE question_categories ADD COLUMN unlocked_by_default BOOLEAN DEFAULT 1")
            )
            db.session.execute(
                text("UPDATE question_categories SET unlocked_by_default = 1 WHERE unlocked_by_default IS NULL")
            )
            needs_commit = True

    if "prepared_exercise_sets" in table_names:
        prepared_columns = {
            column["name"] for column in inspector.get_columns("prepared_exercise_sets")
        }

        if "instructions_fr" not in prepared_columns:
            db.session.execute(
                text("ALTER TABLE prepared_exercise_sets ADD COLUMN instructions_fr TEXT")
            )
            needs_commit = True

        if "instructions_en" not in prepared_columns:
            db.session.execute(
                text("ALTER TABLE prepared_exercise_sets ADD COLUMN instructions_en TEXT")
            )
            needs_commit = True

    if "exercise_items" in table_names:
        item_columns = {
            column["name"] for column in inspector.get_columns("exercise_items")
        }

        if "is_active" not in item_columns:
            db.session.execute(
                text("ALTER TABLE exercise_items ADD COLUMN is_active BOOLEAN DEFAULT 1")
            )
            db.session.execute(
                text("UPDATE exercise_items SET is_active = 1 WHERE is_active IS NULL")
            )
            needs_commit = True

    if "session_exercises" in table_names:
        session_ex_columns = {
            column["name"] for column in inspector.get_columns("session_exercises")
        }
        if "question_type" not in session_ex_columns:
            db.session.execute(
                text(
                    "ALTER TABLE session_exercises ADD COLUMN question_type "
                    "VARCHAR(20) DEFAULT 'text'"
                )
            )
            db.session.execute(
                text(
                    "UPDATE session_exercises SET question_type = 'text' "
                    "WHERE question_type IS NULL"
                )
            )
            needs_commit = True
        if "options_json" not in session_ex_columns:
            db.session.execute(
                text("ALTER TABLE session_exercises ADD COLUMN options_json TEXT")
            )
            needs_commit = True
        if "accepted_answers_json" not in session_ex_columns:
            db.session.execute(
                text(
                    "ALTER TABLE session_exercises ADD COLUMN accepted_answers_json TEXT"
                )
            )
            needs_commit = True
        if "source" not in session_ex_columns:
            db.session.execute(
                text(
                    "ALTER TABLE session_exercises ADD COLUMN source "
                    "VARCHAR(20) DEFAULT 'procedural'"
                )
            )
            db.session.execute(
                text(
                    "UPDATE session_exercises SET source = 'procedural' "
                    "WHERE source IS NULL"
                )
            )
            needs_commit = True
        if "ai_exercise_id" not in session_ex_columns:
            db.session.execute(
                text("ALTER TABLE session_exercises ADD COLUMN ai_exercise_id INTEGER")
            )
            needs_commit = True
        if "explanation" not in session_ex_columns:
            db.session.execute(
                text("ALTER TABLE session_exercises ADD COLUMN explanation TEXT")
            )
            needs_commit = True
        if "correction_status" not in session_ex_columns:
            db.session.execute(
                text(
                    "ALTER TABLE session_exercises ADD COLUMN correction_status "
                    "VARCHAR(20) DEFAULT 'incorrect'"
                )
            )
            db.session.execute(
                text(
                    "UPDATE session_exercises SET correction_status = "
                    "CASE WHEN is_correct = 1 THEN 'correct' ELSE 'incorrect' END "
                    "WHERE correction_status IS NULL OR correction_status = 'incorrect'"
                )
            )
            needs_commit = True

    if "ai_generated_exercises" in table_names:
        ai_ex_columns = {
            column["name"] for column in inspector.get_columns("ai_generated_exercises")
        }
        if "explanation" not in ai_ex_columns:
            db.session.execute(
                text("ALTER TABLE ai_generated_exercises ADD COLUMN explanation TEXT")
            )
            needs_commit = True

    if "parent_student" not in table_names:
        db.session.execute(
            text(
                "CREATE TABLE parent_student ("
                "parent_id INTEGER NOT NULL REFERENCES students(id), "
                "student_id INTEGER NOT NULL REFERENCES students(id), "
                "PRIMARY KEY (parent_id, student_id))"
            )
        )
        needs_commit = True

    if needs_commit:
        db.session.commit()

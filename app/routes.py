from collections import Counter, defaultdict
import calendar
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

import csv
import json
import re

from flask import (
    Blueprint,
    abort,
    flash,
    current_app,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from werkzeug.utils import secure_filename

try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from . import db, limiter
from .config import Config
from .exercise_factory import (
    ExercisePrompt,
    DIFFICULTY_LABELS,
    DIFFICULTY_LEVELS,
    generate_default_exercises,
    generate_exercises_for_categories,
    normalize_difficulty,
    AVAILABLE_CATEGORIES,
)
from .models import (
    AICallLog,
    AIGeneratedExercise,
    AppConfig,
    Badge,
    EmailConfig,
    OpenAIConfig,
    OpenAIPrompt,
    _safe_format,
    PracticeSession,
    PreparedExercise,
    PreparedExerciseQuestion,
    PreparedExerciseSet,
    ExerciseItem,
    QuestionCategory,
    ReviewPlan,
    SessionExercise,
    SessionTranslationLog,
    SkillPrerequisite,
    Student,
    StudentBadge,
    StudentSkillProgress,
    WeeklyGoal,
    WordTranslation,
)
from .services.auth import (
    _admin_required,
    _assert_student_access,
    _current_user,
    _get_student_or_404,
    _get_visible_students,
    _load_user_from_session,
    _login_required,
    _login_user,
    _logout_user,
    _parent_required,
    is_safe_url,
    require_login,
)
from .services.analytics import (
    _build_simple_pdf,
    _pdf_escape,
    _quarter_range,
    _student_recurring_errors,
    _student_theme_summary,
)
from .services.answer_validation import (
    _accepted_answers,
    _is_answer_correct,
    _normalize_answer,
    _prompt_has_blank,
    _session_exercise_kwargs,
    _strip_article,
)
from .services.curriculum import (
    DOMAIN_CHOICES,
    _category_in_target,
    _category_priority,
    _build_prerequisite_map,
    _cefr_rank,
    _difficulty_from_cefr,
    _domain_list,
    _filter_categories,
    _grade_rank,
    _is_category_unlocked,
    _load_progress_map,
    _parse_domain_list,
    _recommend_difficulty,
)
from .services.gamification import (
    DIFFICULTY_XP,
    LEVEL_TITLES,
    _award_badges,
    _compute_activity_heatmap,
    _compute_global_streak,
    _compute_weekly_progress,
    _compute_xp_and_level,
    _current_week_range,
    _get_weekly_goal,
    _review_interval_days,
    _select_instruction_language,
    _update_progress_from_session,
    _update_review_plan,
    _week_start,
)
from .services.imports import _parse_import_rows
from .validators import (
    validate_name,
    validate_email,
    validate_age,
    validate_goals,
    validate_password,
    sanitize_text_input,
    validate_question_content,
)

bp = Blueprint("main", __name__)

DIFFICULTY_DISPLAY = {**DIFFICULTY_LABELS, "prepared": "Parcours préparé"}
DIFFICULTY_CHOICES = [(value, DIFFICULTY_LABELS[value]) for value in DIFFICULTY_LEVELS]
CEFR_LEVELS = ["A1", "A2"]
GRADE_LEVELS = ["6e", "5e"]
TRIMESTER_CHOICES = [1, 2, 3]
SESSION_TYPE_LABELS = {
    "practice": "Entraînement",
    "challenge": "Défi",
    "control": "Contrôle",
    "prepared": "Parcours préparé",
    "ai_custom": "Prompt libre (IA)",
}

def _csv_safe(value) -> str:
    """Préfixe les cellules CSV commençant par un caractère de formule (=, +, -, @, |, %)
    pour prévenir l'injection de formules dans Excel / LibreOffice."""
    s = str(value) if value is not None else ""
    if s and s[0] in ('=', '+', '-', '@', '|', '%'):
        return "'" + s
    return s


def validate_image_file(file):
    """Validation stricte des fichiers image"""
    if not file or not file.filename:
        return False
    
    # Vérifier l'extension
    sanitized = secure_filename(file.filename)
    extension = sanitized.rsplit(".", 1)[-1].lower() if "." in sanitized else ""
    if extension not in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
        return False
    
    # Vérifier le type MIME réel si python-magic est disponible
    if MAGIC_AVAILABLE:
        file_type = magic.from_buffer(file.read(1024), mime=True)
        file.seek(0)
        if file_type not in ['image/jpeg', 'image/png', 'image/gif']:
            return False
    
    # Vérifier que c'est vraiment une image si PIL est disponible
    if PIL_AVAILABLE:
        try:
            Image.open(file).verify()
            file.seek(0)
            return True
        except Exception:
            return False
    
    return True


bp.before_app_request(require_login)


def _slugify_label(label: str) -> str:
    slug = secure_filename(label.lower())
    return slug.replace("-", "_") or f"category_{uuid4().hex[:6]}"


def _delete_avatar_file(filename: Optional[str]) -> None:
    if not filename:
        return
    upload_folder = Path(current_app.config["UPLOAD_FOLDER"])
    candidate = upload_folder / filename
    if candidate.exists():
        try:
            candidate.unlink()
        except OSError:
            current_app.logger.warning("Impossible de supprimer l'ancien avatar %s", candidate)







"""Logique pédagogique : ciblage des catégories selon le profil de l'élève,
prérequis, priorités de recommandation, ajustement dynamique de la
difficulté.

Ces fonctions sont volontairement pures côté Flask (pas d'accès à ``g``
ou ``session``) : le ``user``/``student`` est toujours passé en argument.
"""

from datetime import datetime
from typing import Dict, List, Optional

from ..exercise_factory import DIFFICULTY_LEVELS
from ..models import (
    PracticeSession,
    QuestionCategory,
    SkillPrerequisite,
    Student,
    StudentSkillProgress,
)


# Domaines pédagogiques exposés dans les formulaires d'admin/parent et
# utilisés pour pondérer la recommandation de catégories.
DOMAIN_CHOICES: List[tuple] = [
    ("vocabulary", "Vocabulaire"),
    ("grammar", "Grammaire"),
    ("comprehension", "Compréhension"),
    ("production", "Production"),
    ("culture", "Culture"),
]


def _parse_domain_list(raw_values: List[str]) -> str:
    allowed = {code for code, _ in DOMAIN_CHOICES}
    filtered = [value for value in raw_values if value in allowed]
    return ",".join(filtered)


def _domain_list(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _grade_rank(value: Optional[str]) -> int:
    mapping = {"6e": 1, "5e": 2}
    return mapping.get(value or "", 0)


def _cefr_rank(value: Optional[str]) -> int:
    mapping = {"A1": 1, "A2": 2}
    return mapping.get(value or "", 0)


def _difficulty_from_cefr(level: Optional[str]) -> str:
    mapping = {"A1": "beginner", "A2": "intermediate"}
    if level in mapping:
        return mapping[level]
    return DIFFICULTY_LEVELS[0]


def _category_in_target(category: QuestionCategory, student: Student) -> bool:
    if student.target_cefr_level and category.cecrl_level:
        if _cefr_rank(category.cecrl_level) > _cefr_rank(student.target_cefr_level):
            return False
    if student.target_grade and category.grade_level:
        if _grade_rank(category.grade_level) > _grade_rank(student.target_grade):
            return False
        if student.target_trimester and category.trimester:
            if category.grade_level == student.target_grade and category.trimester > student.target_trimester:
                return False
    return True


def _load_progress_map(student_id: int) -> Dict[int, StudentSkillProgress]:
    entries = StudentSkillProgress.query.filter_by(student_id=student_id).all()
    return {entry.category_id: entry for entry in entries}


def _build_prerequisite_map() -> Dict[int, List[SkillPrerequisite]]:
    prerequisites = SkillPrerequisite.query.all()
    grouped: Dict[int, List[SkillPrerequisite]] = {}
    for item in prerequisites:
        grouped.setdefault(item.category_id, []).append(item)
    return grouped


def _is_category_unlocked(
    category: QuestionCategory,
    progress_map: Dict[int, StudentSkillProgress],
    prereq_map: Dict[int, List[SkillPrerequisite]],
) -> bool:
    if category.unlocked_by_default:
        return True
    prerequisites = prereq_map.get(category.id, [])
    if not prerequisites:
        return False
    for prereq in prerequisites:
        progress = progress_map.get(prereq.prerequisite_id)
        if not progress or progress.mastery < prereq.min_mastery:
            return False
    return True


def _category_priority(
    category: QuestionCategory,
    progress: Optional[StudentSkillProgress],
    preferred_domains: List[str],
) -> float:
    base = 50.0
    if not progress or progress.total_attempts == 0:
        base = 90.0
    else:
        mastery = progress.mastery or 0.0
        base = max(10.0, 100.0 - mastery)
        if progress.last_practiced:
            days_since = max(0, (datetime.utcnow() - progress.last_practiced).days)
            base += min(days_since * 4.0, 40.0)
        if mastery < 60.0:
            base += 15.0
    if category.domain in preferred_domains:
        base *= 1.2
    return base


def _filter_categories(
    domain: str, cefr: str, grade: str, trimester: str
) -> List[QuestionCategory]:
    query = QuestionCategory.query
    if domain:
        query = query.filter_by(domain=domain)
    if cefr:
        query = query.filter_by(cecrl_level=cefr)
    if grade:
        query = query.filter_by(grade_level=grade)
    if trimester:
        try:
            query = query.filter_by(trimester=int(trimester))
        except ValueError:
            pass
    return query.order_by(QuestionCategory.order_index, QuestionCategory.name).all()


def _recommend_difficulty(student: Student) -> str:
    baseline = _difficulty_from_cefr(student.target_cefr_level)
    latest_session = (
        PracticeSession.query.filter_by(student_id=student.id)
        .order_by(PracticeSession.started_at.desc())
        .first()
    )
    if latest_session and latest_session.difficulty in DIFFICULTY_LEVELS:
        baseline = latest_session.difficulty
    recent_sessions = (
        PracticeSession.query.filter_by(student_id=student.id)
        .order_by(PracticeSession.started_at.desc())
        .limit(5)
        .all()
    )
    accuracy_samples = []
    time_samples = []
    for session_obj in recent_sessions:
        if session_obj.total_questions:
            accuracy_samples.append(session_obj.correct_answers / session_obj.total_questions)
        if session_obj.duration_seconds and session_obj.total_questions:
            time_samples.append(session_obj.duration_seconds / session_obj.total_questions)
    if not accuracy_samples:
        return baseline

    avg_accuracy = sum(accuracy_samples) / len(accuracy_samples)
    avg_time = sum(time_samples) / len(time_samples) if time_samples else None

    level_index = DIFFICULTY_LEVELS.index(baseline)
    if avg_accuracy >= 0.85 and (avg_time is None or avg_time <= 35):
        level_index = min(level_index + 1, len(DIFFICULTY_LEVELS) - 1)
    elif avg_accuracy <= 0.6 or (avg_time is not None and avg_time >= 60):
        level_index = max(level_index - 1, 0)
    return DIFFICULTY_LEVELS[level_index]

"""Système de progression : XP, niveaux, streak, heatmap, badges, objectifs
hebdomadaires et plan de révision.

Constantes ``DIFFICULTY_XP`` / ``LEVEL_TITLES`` exportées ici : elles
encodent les règles du jeu et sont donc partie intégrante du service.

Toutes les fonctions sont sans contexte Flask : aucune lecture de ``g`` /
``session``, on passe explicitement ``student`` ou ``student_id``.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, Optional, Tuple

from ..extensions import db
from ..models import (
    Badge,
    PracticeSession,
    QuestionCategory,
    ReviewPlan,
    Student,
    StudentBadge,
    StudentSkillProgress,
    WeeklyGoal,
)


DIFFICULTY_XP: Dict[str, int] = {"beginner": 10, "intermediate": 20, "advanced": 35}

LEVEL_TITLES = [
    (0, "Novice"),
    (5, "Explorateur"),
    (9, "Aventurier"),
    (13, "Expert"),
    (17, "Maître"),
]


def _review_interval_days(mastery: float) -> int:
    if mastery < 50:
        return 1
    if mastery < 70:
        return 3
    if mastery < 85:
        return 7
    return 14


def _week_start(value: date) -> date:
    return value - timedelta(days=value.weekday())


def _current_week_range() -> Tuple[date, date]:
    start = _week_start(date.today())
    end = start + timedelta(days=6)
    return start, end


def _get_weekly_goal(student_id: int, week_start: date) -> Optional[WeeklyGoal]:
    return WeeklyGoal.query.filter_by(student_id=student_id, week_start=week_start).first()


def _compute_weekly_progress(student: Student, week_start: date) -> Dict[str, float]:
    week_end = week_start + timedelta(days=6)
    sessions = (
        PracticeSession.query.filter(
            PracticeSession.student_id == student.id,
            PracticeSession.completed_at.isnot(None),
            PracticeSession.started_at >= datetime.combine(week_start, datetime.min.time()),
            PracticeSession.started_at <= datetime.combine(week_end, datetime.max.time()),
        )
        .all()
    )
    total_questions = sum(session.total_questions or 0 for session in sessions)
    total_correct = sum(session.correct_answers or 0 for session in sessions)
    total_seconds = sum(session.duration_seconds or 0 for session in sessions)
    challenge_count = sum(1 for session in sessions if session.session_type == "challenge")
    average_score = (total_correct / total_questions * 100) if total_questions else 0.0
    return {
        "sessions": len(sessions),
        "minutes": round(total_seconds / 60, 1) if total_seconds else 0.0,
        "accuracy": round(average_score, 1) if average_score else 0.0,
        "challenges": challenge_count,
    }


def _select_instruction_language(student: Student) -> str:
    if student.target_cefr_level and student.target_cefr_level.upper() == "A2":
        return "en"
    return "fr"


def _compute_xp_and_level(sessions: list) -> dict:
    xp = sum(
        (s.correct_answers or 0) * DIFFICULTY_XP.get(s.difficulty or "beginner", 10)
        for s in sessions if s.completed_at
    )
    level = min(20, int((xp / 50) ** 0.5) + 1)
    xp_for_level = (level - 1) ** 2 * 50
    xp_for_next = level ** 2 * 50
    xp_progress_pct = int((xp - xp_for_level) / max(1, xp_for_next - xp_for_level) * 100)
    title = next(t for lvl, t in reversed(LEVEL_TITLES) if level >= lvl)
    return {
        "xp": xp,
        "level": level,
        "title": title,
        "xp_progress_pct": min(100, xp_progress_pct),
        "xp_for_next": xp_for_next,
    }


def _compute_global_streak(sessions: list) -> int:
    completed_dates = {s.started_at.date() for s in sessions if s.completed_at and s.started_at}
    if not completed_dates:
        return 0
    streak = 0
    check_date = date.today()
    while check_date in completed_dates:
        streak += 1
        check_date -= timedelta(days=1)
    return streak


def _compute_activity_heatmap(sessions: list) -> list:
    counts: dict = {}
    for s in sessions:
        if s.completed_at and s.started_at:
            d = s.started_at.date().isoformat()
            counts[d] = counts.get(d, 0) + 1
    today = date.today()
    return [
        {"date": (today - timedelta(days=i)).isoformat(),
         "count": counts.get((today - timedelta(days=i)).isoformat(), 0)}
        for i in range(34, -1, -1)
    ]


def _award_badges(student_id: int) -> None:
    progress_entries = StudentSkillProgress.query.filter_by(student_id=student_id).all()
    progress_map = {entry.category_id: entry for entry in progress_entries}
    badges = Badge.query.all()
    earned = {item.badge_id for item in StudentBadge.query.filter_by(student_id=student_id).all()}
    changed = False
    for badge in badges:
        if badge.id in earned:
            continue
        if badge.category_id is None:
            continue
        progress = progress_map.get(badge.category_id)
        if not progress:
            continue
        if progress.mastery >= badge.min_mastery and progress.correct_streak >= badge.min_streak:
            db.session.add(StudentBadge(student_id=student_id, badge_id=badge.id))
            changed = True
    if changed:
        db.session.flush()


def _update_review_plan(session_obj: PracticeSession) -> None:
    today = date.today()
    categories = {exercise.category for exercise in session_obj.exercises}
    category_lookup = {
        category.code: category for category in QuestionCategory.query.filter(
            QuestionCategory.code.in_(categories)
        ).all()
    }

    for category_code, category in category_lookup.items():
        ReviewPlan.query.filter(
            ReviewPlan.student_id == session_obj.student_id,
            ReviewPlan.category_id == category.id,
            ReviewPlan.due_date <= today,
            ReviewPlan.completed.is_(False),
        ).update({"completed": True})

        progress = StudentSkillProgress.query.filter_by(
            student_id=session_obj.student_id,
            category_id=category.id,
        ).first()
        mastery = progress.mastery if progress else 0.0
        interval = _review_interval_days(mastery)
        for multiplier in (1, 2, 4):
            due_date = today + timedelta(days=interval * multiplier)
            existing = ReviewPlan.query.filter_by(
                student_id=session_obj.student_id,
                category_id=category.id,
                due_date=due_date,
            ).first()
            if not existing:
                db.session.add(
                    ReviewPlan(
                        student_id=session_obj.student_id,
                        category_id=category.id,
                        due_date=due_date,
                    )
                )

    db.session.flush()


def _update_progress_from_session(session_obj: PracticeSession) -> None:
    now = datetime.utcnow()
    category_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"correct": 0, "total": 0})
    for exercise in session_obj.exercises:
        category_stats[exercise.category]["total"] += 1
        if exercise.is_correct:
            category_stats[exercise.category]["correct"] += 1

    categories = QuestionCategory.query.filter(QuestionCategory.code.in_(category_stats.keys())).all()
    category_lookup = {category.code: category for category in categories}

    for category_code, stats in category_stats.items():
        category = category_lookup.get(category_code)
        if not category:
            continue
        progress = StudentSkillProgress.query.filter_by(
            student_id=session_obj.student_id,
            category_id=category.id,
        ).first()
        if not progress:
            progress = StudentSkillProgress(
                student_id=session_obj.student_id,
                category_id=category.id,
            )
            db.session.add(progress)
        if progress.total_attempts is None:
            progress.total_attempts = 0
        if progress.correct_attempts is None:
            progress.correct_attempts = 0
        if progress.correct_streak is None:
            progress.correct_streak = 0
        progress.total_attempts += stats["total"]
        progress.correct_attempts += stats["correct"]
        session_accuracy = (stats["correct"] / stats["total"]) * 100 if stats["total"] else 0.0
        progress.last_accuracy = session_accuracy
        progress.last_practiced = now
        if session_accuracy >= 80:
            progress.correct_streak += 1
        else:
            progress.correct_streak = 0
        progress.mastery = (
            (progress.correct_attempts / progress.total_attempts) * 100
            if progress.total_attempts
            else 0.0
        )

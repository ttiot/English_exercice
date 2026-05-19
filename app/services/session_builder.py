"""Construction de sessions de pratique : factorisation de la génération IA
dupliquée entre ``students.start_session`` (mode "ai_custom") et
``parents.parent_generate_ai_exercises``.

Trois entry points :

- :func:`generate_ai_exercises_for_student` — valide le prompt, vérifie le
  budget + la disponibilité du client OpenAI, appelle ``ai_generator``.
  Lève :class:`AIGenerationError` en cas de problème (avec message déjà
  rédigé et sévérité pour ``flash``).
- :func:`persist_ai_as_practice_session` — crée la ``PracticeSession``
  (mode interactif "play now") + ses ``SessionExercise``.
- :func:`persist_ai_as_prepared_set` — crée un ``PreparedExerciseSet``
  (pool pour usage différé à la prochaine session de l'élève).

Le caller choisit le mode de persistance selon l'usage. Aucune fonction
n'utilise ``flask.session`` / ``g`` : tout est passé en argument explicite,
ce qui rend le service testable sans contexte HTTP.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from ..extensions import db
from ..exercise_factory import ExercisePrompt
from ..models import (
    AIGeneratedExercise,
    PracticeSession,
    PreparedExerciseQuestion,
    PreparedExerciseSet,
    SessionExercise,
    Student,
)
from .answer_validation import _session_exercise_kwargs


# Taille pratique : on tronque silencieusement à 500 ; on rejette en deçà
# de 5 caractères avec un message demandant à l'élève de reformuler.
PROMPT_MIN_LENGTH = 5
PROMPT_MAX_LENGTH = 500


class AIGenerationError(Exception):
    """Erreur de génération IA prête à être flashée.

    L'appelant fait simplement ``flash(exc.message, exc.severity)`` et
    redirige/réaffiche la page.
    """

    def __init__(self, message: str, *, severity: str = "danger") -> None:
        super().__init__(message)
        self.message = message
        self.severity = severity


def generate_ai_exercises_for_student(
    *,
    student_prompt: str,
    difficulty: str,
    question_count: int,
    student: Student,
) -> Tuple[str, List[Tuple[ExercisePrompt, AIGeneratedExercise]]]:
    """Valide le prompt + génère via OpenAI.

    Retourne ``(prompt_nettoye, ai_pairs)`` où ``ai_pairs`` est une liste
    de tuples ``(ExercisePrompt, AIGeneratedExercise)`` produite par
    ``ai_generator.generate_exercises``.

    Lève :class:`AIGenerationError` (que le caller flashe) si :
    - le prompt fait moins de :data:`PROMPT_MIN_LENGTH` caractères,
    - OpenAI n'est pas configuré (aucun client disponible),
    - le budget mensuel est atteint,
    - la génération n'a renvoyé aucun exercice.
    """
    # Import paresseux : le service ai_generator dépend du client OpenAI
    # qui peut être absent en environnement de test.
    from .ai_generator import (
        generate_exercises as ai_generate_exercises,
        get_openai_client,
        is_budget_exceeded,
    )

    prompt = (student_prompt or "").strip()
    if not prompt or len(prompt) < PROMPT_MIN_LENGTH:
        raise AIGenerationError(
            "Décris en quelques mots le sujet sur lequel tu veux travailler "
            f"(au moins {PROMPT_MIN_LENGTH} caractères).",
            severity="warning",
        )
    if len(prompt) > PROMPT_MAX_LENGTH:
        prompt = prompt[:PROMPT_MAX_LENGTH]

    client, _info = get_openai_client()
    if client is None:
        raise AIGenerationError(
            "OpenAI n'est pas configuré. Demande à l'administrateur "
            "d'activer le service IA.",
        )
    if is_budget_exceeded():
        raise AIGenerationError(
            "Le budget mensuel IA est atteint. Réessaie le mois prochain "
            "ou demande à l'administrateur d'augmenter le plafond.",
            severity="warning",
        )

    ai_pairs = ai_generate_exercises(
        student_prompt=prompt,
        count=question_count,
        difficulty=difficulty,
        student_id=student.id,
    )
    if not ai_pairs:
        raise AIGenerationError(
            "Désolé, l'IA n'a pas pu générer d'exercices pour ce thème. "
            "Reformule ou réessaie plus tard.",
        )
    return prompt, ai_pairs


def persist_ai_as_practice_session(
    *,
    student: Student,
    prompt: str,
    ai_pairs: List[Tuple[ExercisePrompt, AIGeneratedExercise]],
    difficulty: str,
    time_limit_value: Optional[int],
) -> PracticeSession:
    """Crée une ``PracticeSession`` interactive depuis les exercices IA.

    Persiste l'objet + ses :class:`SessionExercise` + incrémente
    ``times_used`` sur le pool. Le caller fait ensuite un redirect vers
    ``sessions.play_session``.
    """
    session_obj = PracticeSession(
        student_id=student.id,
        time_limit_minutes=time_limit_value,
        time_limit_seconds=(time_limit_value * 60) if time_limit_value else None,
        total_questions=len(ai_pairs),
        difficulty=difficulty,
        session_type="ai_custom",
        instructions_fr=prompt,
    )
    db.session.add(session_obj)
    db.session.flush()
    for index, (exercise, pool_row) in enumerate(ai_pairs):
        db.session.add(
            SessionExercise(
                session_id=session_obj.id,
                display_order=index,
                **_session_exercise_kwargs(
                    exercise, source="ai", ai_exercise_id=pool_row.id
                ),
            )
        )
        pool_row.times_used = (pool_row.times_used or 0) + 1
    db.session.commit()
    return session_obj


def persist_ai_as_prepared_set(
    *,
    student: Student,
    prompt: str,
    ai_pairs: List[Tuple[ExercisePrompt, AIGeneratedExercise]],
) -> PreparedExerciseSet:
    """Crée un ``PreparedExerciseSet`` réservé à l'élève (pool différé).

    Utilisé par l'écran parent "générer pour mon enfant" : les exercices
    sont stockés pour être proposés lors de la prochaine session
    procédurale, sans démarrer immédiatement une session.
    """
    safe_prompt = prompt[:50]
    exercise_set = PreparedExerciseSet(
        title=f"IA : {safe_prompt}",
        student_id=student.id,
    )
    db.session.add(exercise_set)
    db.session.flush()

    for idx, (ep, _pool_row) in enumerate(ai_pairs):
        db.session.add(
            PreparedExerciseQuestion(
                exercise_set_id=exercise_set.id,
                prompt=ep.prompt,
                answer=ep.answer,
                category_code=ep.category,
                position=idx,
            )
        )

    db.session.commit()
    return exercise_set

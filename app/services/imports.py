"""Import et opérations bulk sur les exercices côté parent.

Centralise trois logiques qui étaient dupliquées (ou orphelines) dans
``blueprints/parents/__init__.py`` :

- :func:`_parse_import_rows` — parsing CSV / TSV / format Anki en lignes
  ``{prompt, answer, category}``.
- :func:`persist_prepared_set` — création d'un :class:`PreparedExerciseSet`
  + ses :class:`PreparedExerciseQuestion`. Utilisé à la fois par la saisie
  manuelle (``create_prepared_exercise``) et par l'import bulk
  (``import_exercises``).
- :func:`parse_batch_selection` / :func:`apply_bulk_change` — gestion des
  sélections multiples du gestionnaire d'exercices unifié
  (``list_all_exercises`` + ``bulk_edit_exercises``).

Toutes les fonctions sont sans contexte Flask : prennent les arguments
explicitement et renvoient soit l'objet créé, soit (objet + warnings).
"""

from __future__ import annotations

import csv
from io import StringIO
from typing import Dict, List, Optional, Tuple

from ..extensions import db
from ..models import (
    ExerciseItem,
    PreparedExerciseQuestion,
    PreparedExerciseSet,
    QuestionCategory,
    SessionExercise,
    Student,
)
from ..validators import sanitize_text_input, validate_question_content


# ---------------------------------------------------------------------------
# Parsing CSV / TSV / Anki
# ---------------------------------------------------------------------------


def _parse_import_rows(
    file_content: str, import_format: str, delimiter: str
) -> List[Dict[str, str]]:
    """Parse le contenu d'un fichier d'import et renvoie une liste de
    ``{prompt, answer, category}``.

    Supporte ``import_format="anki"`` (séparateurs tabulation / virgule /
    point-virgule, 2 ou 3 colonnes) ou CSV avec en-tête optionnel.
    """
    rows: List[Dict[str, str]] = []
    if import_format == "anki":
        for raw_line in file_content.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if "\t" in line:
                parts = [part.strip() for part in line.split("\t", 2)]
            elif ";" in line:
                parts = [part.strip() for part in line.split(";", 2)]
            else:
                parts = [part.strip() for part in line.split(",", 2)]
            if len(parts) < 2:
                continue
            rows.append({"prompt": parts[0], "answer": parts[1], "category": "custom"})
        return rows

    safe_delimiter = (delimiter or ",")[0]
    csv_reader = csv.reader(StringIO(file_content), delimiter=safe_delimiter)
    headers: List[str] = []
    for index, row in enumerate(csv_reader):
        if not row:
            continue
        if index == 0 and any(cell.lower() in {"prompt", "question", "answer", "reponse"} for cell in row):
            headers = [cell.strip().lower() for cell in row]
            continue
        if headers:
            row_map = {headers[i]: row[i].strip() if i < len(row) else "" for i in range(len(headers))}
            prompt = row_map.get("prompt") or row_map.get("question") or ""
            answer = row_map.get("answer") or row_map.get("reponse") or ""
            category = row_map.get("category") or row_map.get("categorie") or "custom"
        else:
            prompt = row[0].strip() if len(row) > 0 else ""
            answer = row[1].strip() if len(row) > 1 else ""
            category = row[2].strip() if len(row) > 2 else "custom"
        if prompt and answer:
            rows.append({"prompt": prompt, "answer": answer, "category": category or "custom"})
    return rows


# ---------------------------------------------------------------------------
# Persistance d'un PreparedExerciseSet
# ---------------------------------------------------------------------------


def persist_prepared_set(
    *,
    title: str,
    student: Optional[Student],
    rows: List[Dict[str, str]],
    instructions_fr: Optional[str] = None,
    instructions_en: Optional[str] = None,
    use_time_limit: bool = False,
    time_limit_seconds: Optional[int] = None,
    valid_category_codes: Optional[set] = None,
    validate_each_row: bool = False,
) -> Tuple[PreparedExerciseSet, List[str]]:
    """Crée un :class:`PreparedExerciseSet` + ses questions à partir de ``rows``.

    Les ``rows`` sont des dicts ``{prompt, answer, category}``. Le contenu
    est systématiquement sanitisé avec ``sanitize_text_input``.

    Paramètres :
    - ``valid_category_codes`` : si fourni (ex. depuis l'import bulk), les
      codes inconnus sont remplacés silencieusement par ``"custom"``.
    - ``validate_each_row`` : si vrai (ex. depuis l'import bulk), applique
      :func:`validate_question_content` à chaque ligne et ignore celles qui
      sont invalides en accumulant un message dans la liste de warnings
      retournée. Si faux (ex. saisie manuelle déjà validée en amont par la
      route), toutes les lignes sont persistées telles quelles.

    Retourne ``(exercise_set, warnings)``. Si ``rows`` est vide, le set est
    quand même créé (vide). Caller responsable du flash + redirect.
    """
    exercise_set = PreparedExerciseSet(
        title=title,
        student=student,
        use_time_limit=use_time_limit,
        time_limit_seconds=time_limit_seconds if use_time_limit else None,
        instructions_fr=instructions_fr,
        instructions_en=instructions_en,
    )
    db.session.add(exercise_set)
    db.session.flush()

    warnings: List[str] = []
    position = 0
    for row in rows:
        prompt = sanitize_text_input(row.get("prompt", ""))
        answer = sanitize_text_input(row.get("answer", ""))
        category_code = (row.get("category") or "custom").strip() or "custom"
        if valid_category_codes is not None and category_code not in valid_category_codes:
            category_code = "custom"

        if not prompt or not answer:
            continue

        if validate_each_row:
            valid, message = validate_question_content(prompt, answer)
            if not valid:
                warnings.append(f"Question ignorée : {message}")
                continue

        db.session.add(
            PreparedExerciseQuestion(
                exercise_set_id=exercise_set.id,
                prompt=prompt,
                answer=answer,
                category_code=category_code,
                position=position,
            )
        )
        position += 1

    db.session.commit()
    return exercise_set, warnings


# ---------------------------------------------------------------------------
# Sélection bulk
# ---------------------------------------------------------------------------


def parse_batch_selection(form, *, key_prefix: str = "item") -> List[Tuple[str, int]]:
    """Extrait la liste ``[(item_type, item_id)]`` d'un form de bulk-edit.

    Le formulaire envoie des paires ``{prefix}_{i}_type`` et
    ``{prefix}_{i}_id`` pour ``i = 0, 1, 2…``. On s'arrête à la première
    paire entièrement absente. Les paires malformées (id non-int) sont
    silencieusement ignorées.
    """
    items: List[Tuple[str, int]] = []
    i = 0
    while True:
        item_type = form.get(f"{key_prefix}_{i}_type")
        item_id_raw = form.get(f"{key_prefix}_{i}_id")
        if item_type is None and item_id_raw is None:
            break
        try:
            items.append((item_type, int(item_id_raw)))
        except (TypeError, ValueError):
            pass
        i += 1
    return items


def apply_bulk_change(
    items: List[Tuple[str, int]],
    field: str,
    value: str,
    *,
    valid_category_codes: Optional[set] = None,
    valid_difficulties: Optional[set] = None,
) -> int:
    """Applique ``field=value`` aux items sélectionnés. Renvoie le nombre
    de modifications réellement appliquées.

    ``field`` doit être ``"category"`` ou ``"difficulty"``. Les items hors
    cible (par exemple ``difficulty`` sur un ``session_exercise``) sont
    silencieusement ignorés — le caller a déjà validé la cohérence de la
    valeur en amont (cf. ``valid_category_codes`` / ``valid_difficulties``).
    """
    cat_by_code = {}
    if valid_category_codes is not None:
        cat_by_code = {
            c.code: c
            for c in QuestionCategory.query.filter(
                QuestionCategory.code.in_(valid_category_codes)
            ).all()
        }

    updated = 0
    for item_type, item_id in items:
        if item_type == "session":
            if field == "category":
                ex = SessionExercise.query.get(item_id)
                if ex:
                    ex.category = value
                    updated += 1
        elif item_type == "prepared":
            if field == "category":
                ex = PreparedExerciseQuestion.query.get(item_id)
                if ex:
                    ex.category_code = value
                    updated += 1
        elif item_type == "bank":
            ex = ExerciseItem.query.get(item_id)
            if ex:
                if field == "category":
                    cat = cat_by_code.get(value)
                    if cat:
                        ex.category_id = cat.id
                        updated += 1
                elif field == "difficulty":
                    ex.difficulty = value
                    updated += 1

    db.session.commit()
    return updated

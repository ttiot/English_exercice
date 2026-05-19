"""Synthèses statistiques par élève + génération de PDF minimaliste pour le
rapport trimestriel à imprimer.

Volontairement sans bibliothèque PDF externe : on écrit un PDF 1.4 valide à
la main pour rester dans la stack ``cryptography + Flask + SQLAlchemy``
sans ajouter de dépendance lourde (reportlab/weasyprint).
"""

import calendar
from collections import defaultdict
from datetime import date
from typing import Dict, List, Tuple

from ..models import PracticeSession, QuestionCategory, SessionExercise
from .curriculum import DOMAIN_CHOICES


def _quarter_range(year: int, quarter: int) -> Tuple[date, date]:
    quarter = max(1, min(4, quarter))
    start_month = (quarter - 1) * 3 + 1
    end_month = start_month + 2
    start = date(year, start_month, 1)
    last_day = calendar.monthrange(year, end_month)[1]
    end = date(year, end_month, last_day)
    return start, end


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_simple_pdf(lines: List[str]) -> bytes:
    content_lines = ["BT", "/F1 12 Tf", "50 780 Td"]
    for line in lines:
        safe = _pdf_escape(line)
        content_lines.append(f"({safe}) Tj")
        content_lines.append("0 -16 Td")
    content_lines.append("ET")
    content = "\n".join(content_lines)

    objects = []
    objects.append("1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj")
    objects.append("2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj")
    objects.append(
        "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >> endobj"
    )
    objects.append(f"4 0 obj << /Length {len(content.encode('utf-8'))} >> stream\n{content}\nendstream endobj")
    objects.append("5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj")

    xref_positions = []
    output = ["%PDF-1.4"]
    offset = len(output[0]) + 1
    for obj in objects:
        xref_positions.append(offset)
        output.append(obj)
        offset += len(obj.encode("utf-8")) + 1

    xref_start = offset
    xref = ["xref", f"0 {len(objects) + 1}", "0000000000 65535 f "]
    for pos in xref_positions:
        xref.append(f"{pos:010} 00000 n ")
    output.extend(xref)
    output.append(
        "trailer << /Size {size} /Root 1 0 R >>".format(size=len(objects) + 1)
    )
    output.append(f"startxref\n{xref_start}\n%%EOF")
    return "\n".join(output).encode("utf-8")


def _student_theme_summary(student_id: int) -> List[Dict[str, object]]:
    exercises = (
        SessionExercise.query.join(PracticeSession)
        .filter(PracticeSession.student_id == student_id)
        .all()
    )
    category_lookup = {
        category.code: category for category in QuestionCategory.query.all()
    }
    domain_labels = {code: label for code, label in DOMAIN_CHOICES}
    stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "correct": 0})
    for exercise in exercises:
        category = category_lookup.get(exercise.category)
        domain = category.domain if category and category.domain else "autre"
        stats[domain]["total"] += 1
        if exercise.is_correct:
            stats[domain]["correct"] += 1
    summary = []
    for domain, values in stats.items():
        total = values["total"]
        correct = values["correct"]
        rate = (correct / total * 100) if total else 0
        summary.append(
            {
                "domain": domain_labels.get(domain, domain),
                "total": total,
                "correct": correct,
                "rate": round(rate, 1) if rate else 0,
            }
        )
    return sorted(summary, key=lambda item: item["domain"])


def _student_recurring_errors(student_id: int, limit: int = 5) -> List[Dict[str, object]]:
    exercises = (
        SessionExercise.query.join(PracticeSession)
        .filter(PracticeSession.student_id == student_id, SessionExercise.is_correct.is_(False))
        .all()
    )
    counts: Dict[str, Dict[str, object]] = {}
    for exercise in exercises:
        key = f"{exercise.category}:{exercise.prompt}"
        entry = counts.setdefault(
            key, {"prompt": exercise.prompt, "category": exercise.category, "count": 0}
        )
        entry["count"] += 1
    sorted_errors = sorted(counts.values(), key=lambda item: item["count"], reverse=True)
    return sorted_errors[:limit]

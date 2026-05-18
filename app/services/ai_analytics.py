"""Analytics et reporting sur les appels OpenAI loggés.

Ce module concentre toute la logique d'aggrégation sur ``AICallLog`` qui
polluait jusqu'ici le modèle (~330 lignes de méthodes statiques). Le modèle
``AICallLog`` redevient un conteneur ORM minimal ; les calculs métier
(coût, statistiques mensuelles, trend annuel, top élèves, taux de succès,
latence moyenne) vivent désormais ici comme fonctions module-level
testables sans instancier de classe.

Fonctions exposées :
- ``calculate_cost(model, input_tokens, output_tokens)`` — coût USD estimé
- ``log_call(...)`` — factory : crée un ``AICallLog`` + ajoute en session
- ``get_monthly_cost_usd(year, month)``
- ``get_monthly_stats(year, month)`` — totals + breakdown par call_type
- ``get_yearly_trend(months)`` — série temporelle pour graphique
- ``get_top_students(limit, year, month)`` — ranking par coût
- ``get_success_stats(year, month)`` — succès / erreurs / taux
- ``get_avg_latency_ms(year, month)``

Constante exportée :
- ``TOKEN_PRICES`` — tarifs USD par 1k tokens (à tenir à jour avec OpenAI).
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from ..extensions import db
from ..models import AICallLog, Student


# Tarifs USD par 1k tokens. Mots-clés cherchés en sous-chaîne dans `model`.
# À tenir à jour selon https://openai.com/api/pricing/.
TOKEN_PRICES = {
    "gpt-5.2": {"input": 0.005, "output": 0.02},
    "gpt-5.1": {"input": 0.004, "output": 0.016},
    "gpt-5-mini": {"input": 0.0003, "output": 0.0012},
    "gpt-5": {"input": 0.003, "output": 0.012},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "gpt-4": {"input": 0.03, "output": 0.06},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    "o1-mini": {"input": 0.003, "output": 0.012},
    "o1": {"input": 0.015, "output": 0.06},
}


def calculate_cost(
    model: str,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
) -> Optional[Decimal]:
    if not model or input_tokens is None or output_tokens is None:
        return None
    model_lower = model.lower()
    prices = None
    for key, value in TOKEN_PRICES.items():
        if key in model_lower:
            prices = value
            break
    if not prices:
        return None
    input_cost = (input_tokens / 1000) * prices.get("input", 0)
    output_cost = (output_tokens / 1000) * prices.get("output", 0)
    return Decimal(str(round(input_cost + output_cost, 6)))


def log_call(
    student_id: Optional[int],
    call_type: str,
    model: str,
    api_key_source: str = "global",
    system_prompt: Optional[str] = None,
    user_prompt: Optional[str] = None,
    response_text: Optional[str] = None,
    response_status: str = "success",
    error_message: Optional[str] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    duration_ms: Optional[int] = None,
    context_json: Optional[str] = None,
) -> AICallLog:
    total_tokens = None
    if input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    log = AICallLog(
        student_id=student_id,
        call_type=call_type,
        model=model,
        api_key_source=api_key_source,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        response_text=response_text,
        response_status=response_status,
        error_message=error_message,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=calculate_cost(model, input_tokens, output_tokens),
        duration_ms=duration_ms,
        context_json=context_json,
    )
    db.session.add(log)
    return log


def get_monthly_cost_usd(
    year: Optional[int] = None, month: Optional[int] = None
) -> Decimal:
    from sqlalchemy import extract, func

    if year is None or month is None:
        now = datetime.utcnow()
        year = now.year
        month = now.month
    result = (
        db.session.query(func.sum(AICallLog.estimated_cost_usd))
        .filter(
            extract("year", AICallLog.created_at) == year,
            extract("month", AICallLog.created_at) == month,
        )
        .scalar()
    )
    return Decimal(str(result)) if result else Decimal("0")


def get_monthly_stats(
    year: Optional[int] = None, month: Optional[int] = None
) -> dict:
    from sqlalchemy import extract, func

    if year is None or month is None:
        now = datetime.utcnow()
        year = now.year
        month = now.month
    totals = (
        db.session.query(
            func.count(AICallLog.id).label("calls"),
            func.sum(AICallLog.input_tokens).label("input_tokens"),
            func.sum(AICallLog.output_tokens).label("output_tokens"),
            func.sum(AICallLog.estimated_cost_usd).label("cost"),
        )
        .filter(
            extract("year", AICallLog.created_at) == year,
            extract("month", AICallLog.created_at) == month,
        )
        .first()
    )
    by_type = (
        db.session.query(
            AICallLog.call_type,
            func.count(AICallLog.id).label("calls"),
            func.sum(AICallLog.estimated_cost_usd).label("cost"),
        )
        .filter(
            extract("year", AICallLog.created_at) == year,
            extract("month", AICallLog.created_at) == month,
        )
        .group_by(AICallLog.call_type)
        .all()
    )
    return {
        "year": year,
        "month": month,
        "calls": totals.calls or 0,
        "input_tokens": int(totals.input_tokens or 0),
        "output_tokens": int(totals.output_tokens or 0),
        "cost_usd": float(totals.cost) if totals.cost else 0.0,
        "by_type": [
            {
                "type": row.call_type,
                "calls": row.calls,
                "cost_usd": float(row.cost) if row.cost else 0.0,
            }
            for row in by_type
        ],
    }


def get_yearly_trend(months: int = 12) -> list:
    """Renvoie une liste chronologique de ``months`` dicts mensuels.

    Chaque entrée : ``{year, month, label, calls, cost_usd, total_tokens}``.
    Trié du plus ancien au plus récent. Les mois sans appel apparaissent
    avec des compteurs à 0.
    """
    from sqlalchemy import extract, func

    now = datetime.utcnow()
    buckets: list = []
    for offset in range(months - 1, -1, -1):
        year = now.year
        month = now.month - offset
        while month <= 0:
            month += 12
            year -= 1
        row = (
            db.session.query(
                func.count(AICallLog.id).label("calls"),
                func.sum(AICallLog.estimated_cost_usd).label("cost"),
                func.sum(AICallLog.total_tokens).label("tokens"),
            )
            .filter(
                extract("year", AICallLog.created_at) == year,
                extract("month", AICallLog.created_at) == month,
            )
            .first()
        )
        buckets.append(
            {
                "year": year,
                "month": month,
                "label": f"{year:04d}-{month:02d}",
                "calls": int(row.calls or 0) if row else 0,
                "cost_usd": float(row.cost) if row and row.cost else 0.0,
                "total_tokens": int(row.tokens or 0) if row else 0,
            }
        )
    return buckets


def get_top_students(
    limit: int = 10,
    year: Optional[int] = None,
    month: Optional[int] = None,
) -> list:
    """Top ``limit`` élèves par coût mensuel (mois courant par défaut)."""
    from sqlalchemy import extract, func

    if year is None or month is None:
        now = datetime.utcnow()
        year = now.year
        month = now.month

    rows = (
        db.session.query(
            AICallLog.student_id,
            func.count(AICallLog.id).label("calls"),
            func.sum(AICallLog.estimated_cost_usd).label("cost"),
            func.sum(AICallLog.total_tokens).label("tokens"),
        )
        .filter(
            AICallLog.student_id.isnot(None),
            extract("year", AICallLog.created_at) == year,
            extract("month", AICallLog.created_at) == month,
        )
        .group_by(AICallLog.student_id)
        .order_by(func.sum(AICallLog.estimated_cost_usd).desc().nullslast())
        .limit(limit)
        .all()
    )
    student_ids = [row.student_id for row in rows]
    students = (
        {s.id: s for s in Student.query.filter(Student.id.in_(student_ids)).all()}
        if student_ids
        else {}
    )
    result = []
    for row in rows:
        student = students.get(row.student_id)
        result.append(
            {
                "student_id": row.student_id,
                "full_name": student.full_name() if student else "—",
                "calls": int(row.calls or 0),
                "cost_usd": float(row.cost) if row.cost else 0.0,
                "total_tokens": int(row.tokens or 0),
            }
        )
    return result


def get_success_stats(
    year: Optional[int] = None, month: Optional[int] = None
) -> dict:
    """Compteurs ``{success, error, total, success_rate}`` pour un mois."""
    from sqlalchemy import extract, func

    if year is None or month is None:
        now = datetime.utcnow()
        year = now.year
        month = now.month

    rows = (
        db.session.query(
            AICallLog.response_status,
            func.count(AICallLog.id).label("count"),
        )
        .filter(
            extract("year", AICallLog.created_at) == year,
            extract("month", AICallLog.created_at) == month,
        )
        .group_by(AICallLog.response_status)
        .all()
    )
    success = sum(r.count for r in rows if r.response_status == "success")
    error = sum(r.count for r in rows if r.response_status != "success")
    total = success + error
    rate = (success / total * 100.0) if total else None
    return {
        "success": success,
        "error": error,
        "total": total,
        "success_rate": rate,
    }


def get_avg_latency_ms(
    year: Optional[int] = None, month: Optional[int] = None
) -> Optional[float]:
    """Latence moyenne (ms) sur les appels du mois ; ``None`` si vide."""
    from sqlalchemy import extract, func

    if year is None or month is None:
        now = datetime.utcnow()
        year = now.year
        month = now.month

    avg = (
        db.session.query(func.avg(AICallLog.duration_ms))
        .filter(
            AICallLog.duration_ms.isnot(None),
            extract("year", AICallLog.created_at) == year,
            extract("month", AICallLog.created_at) == month,
        )
        .scalar()
    )
    return float(avg) if avg is not None else None

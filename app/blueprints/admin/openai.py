"""Routes ``/admin/openai/*`` : configuration et observabilité de l'IA."""

import json
from datetime import datetime
from typing import List

from flask import abort, flash, redirect, render_template, request, url_for

from ...extensions import db
from ...models import AICallLog, OpenAIConfig, OpenAIPrompt, Student
from ...models.utils import _safe_format
from ...services import ai_analytics
from ...services.auth import _admin_required
from ...validators import sanitize_text_input
from . import bp


OPENAI_MODEL_CHOICES = (
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-3.5-turbo",
    "gpt-5-mini",
    "gpt-5",
    "o1-mini",
    "o1",
)


@bp.route("/openai/config", methods=["GET", "POST"])
@_admin_required
def admin_openai_config():
    config = OpenAIConfig.get_or_create()
    test_result = None

    if request.method == "POST":
        action = request.form.get("action", "save")

        if action == "test":
            from ...services.ai_generator import test_connection

            test_result = test_connection()
            if test_result.get("success"):
                flash(
                    "Connexion OpenAI OK. Modèle par défaut : "
                    f"{test_result.get('default_model')}",
                    "success",
                )
            else:
                flash(
                    f"Échec du test : {test_result.get('error', 'erreur inconnue')}",
                    "danger",
                )
        elif action == "clear":
            config.set_api_key(None)
            db.session.commit()
            flash("Clé API supprimée.", "info")
            return redirect(url_for("admin.admin_openai_config"))
        else:  # save
            api_key = request.form.get("api_key", "").strip()
            base_url = request.form.get("base_url", "").strip() or None
            default_model = request.form.get("default_model", "").strip() or None
            source_name = request.form.get("source_name", "").strip() or None
            monthly_budget = request.form.get("monthly_budget", "").strip()
            is_active = bool(request.form.get("is_active"))

            if api_key:
                config.set_api_key(api_key)
            config.base_url = base_url or "https://api.openai.com/v1"
            config.default_model = default_model or "gpt-4o-mini"
            config.source_name = source_name or "OpenAI"
            config.is_active = is_active
            if monthly_budget:
                try:
                    config.monthly_budget_usd = float(monthly_budget)
                except ValueError:
                    flash("Budget mensuel invalide.", "warning")
                    config.monthly_budget_usd = None
            else:
                config.monthly_budget_usd = None

            db.session.commit()
            flash("Configuration OpenAI enregistrée.", "success")
            return redirect(url_for("admin.admin_openai_config"))

    return render_template(
        "admin/openai_config.html",
        config=config,
        model_choices=OPENAI_MODEL_CHOICES,
        test_result=test_result,
    )


@bp.route("/openai/logs")
@_admin_required
def admin_openai_logs():
    from sqlalchemy import desc

    page = max(int(request.args.get("page", 1) or 1), 1)
    per_page = 25
    status = request.args.get("status", "").strip()
    call_type = request.args.get("call_type", "").strip()

    query = AICallLog.query
    if status:
        query = query.filter(AICallLog.response_status == status)
    if call_type:
        query = query.filter(AICallLog.call_type == call_type)
    query = query.order_by(desc(AICallLog.created_at))

    total = query.count()
    logs = query.offset((page - 1) * per_page).limit(per_page).all()
    student_lookup = {
        student.id: student
        for student in Student.query.filter(
            Student.id.in_({log.student_id for log in logs if log.student_id})
        ).all()
    }

    return render_template(
        "admin/openai_logs.html",
        logs=logs,
        student_lookup=student_lookup,
        page=page,
        per_page=per_page,
        total=total,
        status=status,
        call_type=call_type,
    )


@bp.route("/openai/logs/<int:log_id>")
@_admin_required
def admin_openai_log_detail(log_id: int):
    log = AICallLog.query.get_or_404(log_id)
    student = Student.query.get(log.student_id) if log.student_id else None
    return render_template(
        "admin/openai_log_detail.html",
        log=log,
        student=student,
    )


@bp.route("/openai/budget")
@_admin_required
def admin_openai_budget():
    config = OpenAIConfig.get_active()
    today = datetime.utcnow()
    months: List[dict] = []
    for offset in range(0, 3):
        year = today.year
        month = today.month - offset
        while month <= 0:
            month += 12
            year -= 1
        months.append(ai_analytics.get_monthly_stats(year=year, month=month))

    current = months[0]
    budget = float(config.monthly_budget_usd) if config and config.monthly_budget_usd else None
    spent = float(current.get("cost_usd") or 0.0)
    ratio = (spent / budget * 100) if budget else None

    return render_template(
        "admin/openai_budget.html",
        config=config,
        months=months,
        budget=budget,
        spent=spent,
        ratio=ratio,
    )


@bp.route("/openai/")
@_admin_required
def admin_openai_hub():
    """Page d'accueil du panneau d'administration OpenAI."""
    config = OpenAIConfig.get_active()
    current = ai_analytics.get_monthly_stats()
    success_stats = ai_analytics.get_success_stats()
    avg_latency = ai_analytics.get_avg_latency_ms()
    has_key = bool(config and config.get_api_key())
    budget = float(config.monthly_budget_usd) if config and config.monthly_budget_usd else None
    spent = float(current.get("cost_usd") or 0.0)
    budget_ratio = (spent / budget * 100) if budget else None

    return render_template(
        "admin/openai_hub.html",
        config=config,
        has_key=has_key,
        current=current,
        success_stats=success_stats,
        avg_latency=avg_latency,
        budget=budget,
        spent=spent,
        budget_ratio=budget_ratio,
    )


@bp.route("/openai/prompts")
@_admin_required
def admin_openai_prompts():
    """Liste des prompts éditables."""
    from ...services.ai_generator import _DEFAULT_PROMPTS

    for key in _DEFAULT_PROMPTS:
        OpenAIPrompt.get_or_create_default(key)

    prompts = OpenAIPrompt.query.order_by(OpenAIPrompt.prompt_key.asc()).all()
    return render_template(
        "admin/openai_prompts.html",
        prompts=prompts,
        default_keys=set(_DEFAULT_PROMPTS.keys()),
    )


@bp.route("/openai/prompts/<prompt_key>", methods=["GET", "POST"])
@_admin_required
def admin_openai_prompt_edit(prompt_key: str):
    """Édition du prompt système / utilisateur / paramètres."""
    prompt = OpenAIPrompt.get_or_create_default(prompt_key)
    if not prompt:
        abort(404)

    if request.method == "POST":
        display_name = sanitize_text_input(request.form.get("display_name", ""))
        description = sanitize_text_input(request.form.get("description", ""))
        # Pas de sanitize sur les prompts : on veut préserver le formatage
        # (sauts de ligne, accolades de templating, etc.). On limite juste
        # la longueur pour éviter une surcharge.
        system_prompt = (request.form.get("system_prompt") or "")[:20000]
        user_prompt_template = (request.form.get("user_prompt_template") or "")[:20000]
        max_tokens_raw = request.form.get("max_output_tokens", "").strip()
        is_active = bool(request.form.get("is_active"))

        def _validate_template(tmpl: str) -> bool:
            try:
                _safe_format(tmpl)
            except ValueError:
                return False
            except (KeyError, IndexError):
                pass
            return True

        if not display_name:
            flash("Le nom d'affichage est requis.", "warning")
        elif not system_prompt or not user_prompt_template:
            flash("Le prompt système et le prompt utilisateur sont requis.", "warning")
        elif not _validate_template(system_prompt) or not _validate_template(user_prompt_template):
            flash("Le template contient des placeholders non autorisés (accès attribut/index interdit).", "danger")
        else:
            prompt.display_name = display_name
            prompt.description = description or None
            prompt.system_prompt = system_prompt
            prompt.user_prompt_template = user_prompt_template
            prompt.is_active = is_active

            params = prompt.get_parameters()
            if max_tokens_raw:
                try:
                    params["max_output_tokens"] = max(64, min(int(max_tokens_raw), 16000))
                except ValueError:
                    flash("Nombre de tokens max invalide, ignoré.", "warning")
            prompt.parameters_json = json.dumps(params) if params else None

            db.session.commit()
            flash("Prompt enregistré.", "success")
            return redirect(url_for("admin.admin_openai_prompt_edit", prompt_key=prompt_key))

    from ...services.ai_generator import _DEFAULT_PROMPTS

    return render_template(
        "admin/openai_prompt_edit.html",
        prompt=prompt,
        is_default_known=prompt_key in _DEFAULT_PROMPTS,
        max_output_tokens=int(prompt.get_parameters().get("max_output_tokens") or 2000),
        available_variables=prompt.get_available_variables(),
    )


@bp.route("/openai/prompts/<prompt_key>/reset", methods=["POST"])
@_admin_required
def admin_openai_prompt_reset(prompt_key: str):
    """Restaure les valeurs par défaut hardcodées pour ce prompt."""
    prompt = OpenAIPrompt.query.filter_by(prompt_key=prompt_key).first()
    if not prompt:
        abort(404)
    if prompt.reset_to_default():
        db.session.commit()
        flash("Prompt réinitialisé aux valeurs par défaut.", "success")
    else:
        flash("Aucune valeur par défaut connue pour cette clé.", "warning")
    return redirect(url_for("admin.admin_openai_prompt_edit", prompt_key=prompt_key))


@bp.route("/openai/statistics")
@_admin_required
def admin_openai_statistics():
    """Tableau de bord d'usage OpenAI : trend annuel, top élèves, taux de succès."""
    config = OpenAIConfig.get_active()
    current = ai_analytics.get_monthly_stats()
    success_stats = ai_analytics.get_success_stats()
    avg_latency = ai_analytics.get_avg_latency_ms()
    trend = ai_analytics.get_yearly_trend(months=12)
    top_students = ai_analytics.get_top_students(limit=10)

    budget = float(config.monthly_budget_usd) if config and config.monthly_budget_usd else None
    spent = float(current.get("cost_usd") or 0.0)
    budget_ratio = (spent / budget * 100) if budget else None

    return render_template(
        "admin/openai_statistics.html",
        config=config,
        current=current,
        success_stats=success_stats,
        avg_latency=avg_latency,
        trend=trend,
        trend_labels=[bucket["label"] for bucket in trend],
        trend_calls=[bucket["calls"] for bucket in trend],
        trend_costs=[round(bucket["cost_usd"], 4) for bucket in trend],
        top_students=top_students,
        budget=budget,
        spent=spent,
        budget_ratio=budget_ratio,
    )

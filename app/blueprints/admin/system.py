"""Routes ``/admin/system``, ``/admin/email/config`` et ``/admin/config`` :
configuration globale (backup, SMTP, hub d'admin).
"""

from flask import flash, redirect, render_template, request, url_for

from ...extensions import db
from ...models import AppConfig, EmailConfig
from ...services.auth import _admin_required, _current_user
from ...validators import sanitize_text_input
from . import bp


@bp.route("/system", methods=["GET", "POST"])
@_admin_required
def admin_system_config():
    """Configuration système : clé de chiffrement des sauvegardes, etc."""
    app_config = AppConfig.get_or_create()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "save_backup_key":
            raw_key = request.form.get("backup_key", "").strip()
            if raw_key:
                app_config.set_backup_key(raw_key)
                db.session.commit()
                if app_config.export_key_file():
                    flash("Clé de chiffrement backup enregistrée et exportée.", "success")
                else:
                    flash("Clé enregistrée en base, mais l'export vers /data/.backup_key a échoué.", "warning")
            else:
                flash("La clé ne peut pas être vide.", "warning")

        elif action == "clear_backup_key":
            app_config.set_backup_key(None)
            db.session.commit()
            app_config.export_key_file()
            flash("Clé de chiffrement backup supprimée.", "info")

        elif action == "generate_backup_key":
            from cryptography.fernet import Fernet
            new_key = Fernet.generate_key().decode()
            app_config.set_backup_key(new_key)
            db.session.commit()
            if app_config.export_key_file():
                flash(f"Nouvelle clé générée et exportée. Copiez-la maintenant : {new_key}", "success")
            else:
                flash(f"Nouvelle clé générée : {new_key}. Export vers /data/.backup_key a échoué.", "warning")

        return redirect(url_for("admin.admin_system_config"))

    has_backup_key = bool(app_config.backup_key_encrypted)
    return render_template(
        "admin/app_config.html",
        app_config=app_config,
        has_backup_key=has_backup_key,
    )


@bp.route("/email/config", methods=["GET", "POST"])
@_admin_required
def admin_email_config():
    """Configuration du serveur SMTP pour l'envoi d'emails."""
    from ...email_service import send_email, test_smtp_connection

    config = EmailConfig.get_or_create()
    test_result = None

    if request.method == "POST":
        action = request.form.get("action", "save")

        if action == "save":
            config.host = sanitize_text_input(request.form.get("host", "")).strip()
            try:
                config.port = int(request.form.get("port") or 587)
            except ValueError:
                config.port = 587
            config.use_tls = request.form.get("use_tls") == "on"
            config.use_ssl = request.form.get("use_ssl") == "on"
            config.username = sanitize_text_input(request.form.get("username", "")).strip()
            pwd = request.form.get("password", "").strip()
            if pwd:
                config.set_password(pwd)
            config.from_address = sanitize_text_input(request.form.get("from_address", "")).strip()
            config.from_name = sanitize_text_input(request.form.get("from_name", "")).strip()
            config.is_active = request.form.get("is_active") == "on"
            db.session.commit()
            flash("Configuration email enregistrée.", "success")
            return redirect(url_for("admin.admin_email_config"))

        elif action == "test":
            success, msg = test_smtp_connection(config)
            admin = _current_user()
            if success and admin and admin.email:
                send_email(
                    admin.email,
                    "Test email — English Explorer",
                    "<p>La configuration SMTP fonctionne correctement ✓</p>",
                    "La configuration SMTP fonctionne correctement.",
                )
                msg += f" Un email de test a été envoyé à {admin.email}."
            test_result = {"success": success, "message": msg}

        elif action == "clear_password":
            config.set_password(None)
            db.session.commit()
            flash("Mot de passe SMTP supprimé.", "info")
            return redirect(url_for("admin.admin_email_config"))

    return render_template(
        "admin/email_config.html",
        config=config,
        test_result=test_result,
    )


@bp.route("/config")
@_admin_required
def admin_config_hub():
    """Hub de configuration système et email."""
    return render_template("admin/config_hub.html")

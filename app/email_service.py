"""Service d'envoi d'emails via SMTP (stdlib smtplib).

Toutes les fonctions sont non-bloquantes côté appelant : elles retournent
un booléen et loguent les erreurs sans propager d'exceptions.
"""

import hashlib
import secrets
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional


def generate_reset_token() -> tuple[str, str]:
    """Retourne (token_brut, hash_sha256) — stocker uniquement le hash en DB."""
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    return token, token_hash


def _build_connection(config) -> smtplib.SMTP:
    """Crée et authentifie une connexion SMTP selon la config EmailConfig."""
    if config.use_ssl:
        context = ssl.create_default_context()
        conn = smtplib.SMTP_SSL(config.host, config.port, context=context, timeout=10)
    else:
        conn = smtplib.SMTP(config.host, config.port, timeout=10)
        if config.use_tls:
            conn.starttls(context=ssl.create_default_context())

    if config.username:
        password = config.get_password() or ""
        conn.login(config.username, password)

    return conn


def test_smtp_connection(config) -> tuple[bool, str]:
    """Teste la connexion SMTP sans envoyer de message.

    Retourne (succès, message lisible).
    """
    if not config.host:
        return False, "Aucun serveur SMTP configuré."
    try:
        conn = _build_connection(config)
        conn.quit()
        return True, f"Connexion réussie sur {config.host}:{config.port}."
    except smtplib.SMTPAuthenticationError:
        return False, "Authentification échouée : vérifiez l'identifiant et le mot de passe."
    except smtplib.SMTPConnectError as exc:
        return False, f"Impossible de se connecter : {exc}"
    except smtplib.SMTPException as exc:
        return False, f"Erreur SMTP : {exc}"
    except OSError as exc:
        return False, f"Erreur réseau : {exc}"


def send_email(
    to_address: str,
    subject: str,
    body_html: str,
    body_text: Optional[str] = None,
) -> tuple[bool, Optional[str]]:
    """Envoie un email via la configuration SMTP active.

    Retourne (succès, message_erreur_ou_None).
    """
    from flask import current_app
    from .models import EmailConfig

    config = EmailConfig.get_active()
    if config is None:
        return False, "Configuration email non active."

    from_addr = config.from_address or config.username or ""
    if not from_addr:
        return False, "Adresse expéditeur non configurée."

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{config.from_name} <{from_addr}>" if config.from_name else from_addr
    msg["To"] = to_address

    if body_text:
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    try:
        conn = _build_connection(config)
        conn.sendmail(from_addr, [to_address], msg.as_string())
        conn.quit()
        return True, None
    except smtplib.SMTPRecipientsRefused:
        return False, f"Adresse destinataire refusée : {to_address}"
    except smtplib.SMTPException as exc:
        current_app.logger.error("Erreur SMTP lors de l'envoi à %s : %s", to_address, exc)
        return False, str(exc)
    except OSError as exc:
        current_app.logger.error("Erreur réseau lors de l'envoi à %s : %s", to_address, exc)
        return False, str(exc)


def send_password_reset_email(student, token: str, reset_url: str) -> bool:
    """Envoie un email de réinitialisation de mot de passe."""
    prenom = student.first_name
    subject = "Réinitialisation de votre mot de passe — English Explorer"
    body_html = f"""
<p>Bonjour {prenom},</p>
<p>Vous avez demandé la réinitialisation de votre mot de passe sur <strong>English Explorer</strong>.</p>
<p>Cliquez sur le lien ci-dessous pour choisir un nouveau mot de passe (valable <strong>1 heure</strong>) :</p>
<p><a href="{reset_url}">{reset_url}</a></p>
<p>Si vous n'êtes pas à l'origine de cette demande, ignorez cet email — votre mot de passe reste inchangé.</p>
<hr>
<p style="color:#888;font-size:0.85em;">English Explorer — application d'anglais</p>
"""
    body_text = (
        f"Bonjour {prenom},\n\n"
        f"Réinitialisez votre mot de passe English Explorer ici (valable 1 heure) :\n{reset_url}\n\n"
        "Si vous n'êtes pas à l'origine de cette demande, ignorez cet email."
    )
    success, _ = send_email(student.email, subject, body_html, body_text)
    return success


def send_session_completion_email(session_obj) -> bool:
    """Envoie un email récapitulatif de session à l'élève."""
    from flask import current_app

    student = session_obj.student
    if not student or not student.email:
        return False

    total = session_obj.total_questions or 0
    correct = session_obj.correct_answers or 0
    score_pct = int(session_obj.completion_rate())
    prenom = student.first_name

    # Récupérer le nom de catégorie si disponible
    category_name = ""
    if session_obj.exercises:
        first_ex = session_obj.exercises[0]
        if hasattr(first_ex, "category") and first_ex.category:
            category_name = first_ex.category.display_name or ""

    subject = f"Ta session English Explorer est terminée ! Score : {correct}/{total}"
    body_html = f"""
<p>Bravo {prenom} !</p>
<p>Tu viens de terminer une session d'entraînement sur <strong>English Explorer</strong>.</p>
<table style="border-collapse:collapse;margin:1em 0;">
  <tr><td style="padding:4px 12px 4px 0;font-weight:bold;">Score :</td>
      <td style="padding:4px 0;">{correct} / {total} ({score_pct} %)</td></tr>
  {'<tr><td style="padding:4px 12px 4px 0;font-weight:bold;">Catégorie :</td>'
   f'<td style="padding:4px 0;">{category_name}</td></tr>' if category_name else ""}
</table>
<p>Continue comme ça, et tu progresseras vite en anglais !</p>
<hr>
<p style="color:#888;font-size:0.85em;">English Explorer — application d'anglais</p>
"""
    body_text = (
        f"Bravo {prenom} !\n\n"
        f"Session terminée — Score : {correct}/{total} ({score_pct} %)"
        + (f"\nCatégorie : {category_name}" if category_name else "")
        + "\n\nContinue comme ça !"
    )
    success, err = send_email(student.email, subject, body_html, body_text)
    if not success and err:
        current_app.logger.warning(
            "Email fin de session non envoyé pour student %s : %s", student.id, err
        )
    return success

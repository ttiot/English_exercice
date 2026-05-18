"""Singletons de configuration applicative : AppConfig, EmailConfig.

Nommé ``app_settings`` plutôt que ``config`` pour éviter la collision avec
``app/config.py`` (la classe ``Config`` de Flask).
"""

from typing import Optional

from ..extensions import db
from .core import TimestampMixin


class AppConfig(db.Model, TimestampMixin):
    """Singleton de configuration applicative modifiable depuis l'admin.

    La clé de chiffrement des sauvegardes est stockée chiffrée (Fernet).
    À la sauvegarde, la clé en clair est également écrite dans
    ``<DATA_DIR>/.backup_key`` pour que le conteneur de backup puisse l'utiliser.
    """

    __tablename__ = "app_config"

    id = db.Column(db.Integer, primary_key=True)
    backup_key_encrypted = db.Column(db.Text, nullable=True)

    def set_backup_key(self, key: Optional[str]) -> None:
        """Chiffre et stocke la clé de backup. Vide/None supprime la clé."""
        if not key:
            self.backup_key_encrypted = None
            return
        from cryptography.fernet import Fernet
        from flask import current_app
        fernet_key = current_app.config.get("FERNET_KEY")
        if not fernet_key:
            current_app.logger.warning("FERNET_KEY non définie, clé de backup non chiffrée.")
            return
        if isinstance(fernet_key, str):
            fernet_key = fernet_key.encode()
        self.backup_key_encrypted = Fernet(fernet_key).encrypt(key.encode()).decode()

    def get_backup_key(self) -> Optional[str]:
        """Retourne la clé de backup en clair, ou None si absente/illisible."""
        if not self.backup_key_encrypted:
            return None
        from cryptography.fernet import Fernet
        from flask import current_app
        fernet_key = current_app.config.get("FERNET_KEY")
        if not fernet_key:
            return None
        if isinstance(fernet_key, str):
            fernet_key = fernet_key.encode()
        try:
            return Fernet(fernet_key).decrypt(self.backup_key_encrypted.encode()).decode()
        except Exception:
            return None

    def export_key_file(self) -> bool:
        """Écrit la clé en clair dans DATA_DIR/.backup_key pour le conteneur backup.

        Retourne True si l'export a réussi, False sinon.
        """
        from flask import current_app
        from pathlib import Path
        key = self.get_backup_key()
        data_dir = Path(current_app.config.get("DATA_DIR", "/data"))
        key_path = data_dir / ".backup_key"
        try:
            if key:
                key_path.write_text(key)
                key_path.chmod(0o600)
            elif key_path.exists():
                key_path.unlink()
            return True
        except Exception as exc:
            current_app.logger.error("Impossible d'exporter .backup_key : %s", exc)
            return False

    @staticmethod
    def get_or_create() -> "AppConfig":
        config = AppConfig.query.first()
        if not config:
            config = AppConfig()
            db.session.add(config)
            db.session.commit()
        return config


class EmailConfig(db.Model, TimestampMixin):
    """Singleton de configuration SMTP pour l'envoi d'emails (mot de passe oublié, fin de session…).

    Le mot de passe SMTP est chiffré avec Fernet (même clé que OpenAIConfig).
    Si `is_active` est False, aucun email n'est envoyé.
    """

    __tablename__ = "email_config"

    id = db.Column(db.Integer, primary_key=True)
    host = db.Column(db.String(255), nullable=False, default="")
    port = db.Column(db.Integer, default=587)
    use_tls = db.Column(db.Boolean, default=True)   # STARTTLS
    use_ssl = db.Column(db.Boolean, default=False)  # SSL/TLS direct
    username = db.Column(db.String(255), nullable=True)
    password_encrypted = db.Column(db.Text, nullable=True)
    from_address = db.Column(db.String(255), nullable=True)
    from_name = db.Column(db.String(100), nullable=True, default="English Explorer")
    is_active = db.Column(db.Boolean, default=False, nullable=False)

    def set_password(self, password: Optional[str]) -> None:
        """Chiffre et stocke le mot de passe SMTP. Vide/None supprime."""
        if not password:
            self.password_encrypted = None
            return
        from cryptography.fernet import Fernet
        from flask import current_app
        fernet_key = current_app.config.get("FERNET_KEY")
        if not fernet_key:
            current_app.logger.warning("FERNET_KEY non définie, mot de passe SMTP non chiffré.")
            return
        if isinstance(fernet_key, str):
            fernet_key = fernet_key.encode()
        self.password_encrypted = Fernet(fernet_key).encrypt(password.encode()).decode()

    def get_password(self) -> Optional[str]:
        """Retourne le mot de passe SMTP en clair, ou None si absent/illisible."""
        if not self.password_encrypted:
            return None
        from cryptography.fernet import Fernet
        from flask import current_app
        fernet_key = current_app.config.get("FERNET_KEY")
        if not fernet_key:
            return None
        if isinstance(fernet_key, str):
            fernet_key = fernet_key.encode()
        try:
            return Fernet(fernet_key).decrypt(self.password_encrypted.encode()).decode()
        except Exception:
            return None

    @staticmethod
    def get_active() -> Optional["EmailConfig"]:
        return EmailConfig.query.filter_by(is_active=True).first()

    @staticmethod
    def get_or_create() -> "EmailConfig":
        config = EmailConfig.query.first()
        if not config:
            config = EmailConfig()
            db.session.add(config)
            db.session.commit()
        return config

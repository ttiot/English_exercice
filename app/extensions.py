"""Instances partagées des extensions Flask.

Isoler `db`, `migrate`, `csrf` et `limiter` ici (plutôt que dans `app/__init__.py`)
évite les imports circulaires lorsque des modules services voudront accéder à
la session SQLAlchemy sans dépendre du package `app` complet — ce qui devient
indispensable une fois que les routes seront éclatées en blueprints.
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect


db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=[])

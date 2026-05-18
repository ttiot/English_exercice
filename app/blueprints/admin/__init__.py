"""Blueprint ``admin`` : panneau d'administration.

Le blueprint est unique mais ses routes sont éclatées en trois sous-modules
pour rester navigables :
- ``users.py``  : 8 routes de gestion des comptes (rôles, impersonation,
                  rattachement parent↔élèves, CRUD)
- ``openai.py`` : 9 routes côté IA (config, logs, budget, prompts, stats)
- ``system.py`` : 3 routes config système (backup, email, hub)

Préfixe : ``/admin``.
"""

from flask import Blueprint


bp = Blueprint("admin", __name__, url_prefix="/admin")


# L'import des sous-modules a pour effet de bord d'enregistrer les routes sur
# ``bp`` via leur ``@bp.route(...)``. À placer après la création de ``bp`` pour
# éviter une circularité.
from . import openai, system, users  # noqa: E402,F401

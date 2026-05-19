"""Helpers communs aux modèles (sans dépendance SQLAlchemy)."""

import re
import string


_SIMPLE_PLACEHOLDER = re.compile(r'^\w+$')


def _safe_format(template: str, **ctx) -> str:
    """Variante sécurisée de str.format() : n'autorise que les identifiants
    simples (pas d'accès attribut/index) pour prévenir l'injection SSTI."""
    for _, field_name, _, _ in string.Formatter().parse(template):
        if field_name is None:
            continue
        base = field_name.split('.')[0].split('[')[0]
        if not _SIMPLE_PLACEHOLDER.match(base) or '.' in field_name or '[' in field_name:
            raise ValueError(f"Placeholder non autorisé : {{{field_name}}}")
    return template.format(**ctx)

"""
Validation stricte des entrées utilisateur pour la sécurité
"""
import re
from typing import Optional


def validate_name(name: str) -> bool:
    """Valider un nom (prénom/nom de famille)"""
    if not name or len(name.strip()) == 0:
        return False
    
    # Autoriser seulement lettres, espaces, tirets et accents
    pattern = r'^[a-zA-ZÀ-ÿ\s\-\']{1,50}$'
    return bool(re.match(pattern, name.strip()))


def validate_email(email: str) -> bool:
    """Valider une adresse email"""
    if not email or len(email.strip()) == 0:
        return False
    
    # Pattern email basique mais sécurisé
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email.strip().lower())) and len(email) <= 255


def validate_age(age_str: str) -> Optional[int]:
    """Valider et convertir un âge"""
    if not age_str or not age_str.strip():
        return None
    
    try:
        age = int(age_str.strip())
        if 3 <= age <= 120:  # Âge raisonnable
            return age
    except ValueError:
        pass
    
    return None


def validate_goals(goals: str) -> bool:
    """Valider les objectifs d'apprentissage"""
    if not goals:
        return True  # Optionnel
    
    # Limiter la longueur et interdire certains caractères dangereux
    if len(goals.strip()) > 500:
        return False
    
    # Interdire les balises HTML et scripts
    dangerous_patterns = [
        r'<script',
        r'javascript:',
        r'on\w+\s*=',
        r'<iframe',
        r'<object',
        r'<embed'
    ]
    
    goals_lower = goals.lower()
    for pattern in dangerous_patterns:
        if re.search(pattern, goals_lower):
            return False
    
    return True


def validate_password(password: str) -> tuple[bool, str]:
    """Valider un mot de passe et retourner le résultat avec un message"""
    if not password:
        return False, "Le mot de passe est requis"
    
    if len(password) < 12:
        return False, "Le mot de passe doit contenir au moins 12 caractères"
    
    if len(password) > 128:
        return False, "Le mot de passe est trop long (maximum 128 caractères)"
    
    # Vérifier la complexité
    has_lower = bool(re.search(r'[a-z]', password))
    has_upper = bool(re.search(r'[A-Z]', password))
    has_digit = bool(re.search(r'\d', password))
    has_special = bool(re.search(r'[!@#$%^&*(),.?":{}|<>]', password))
    
    complexity_count = sum([has_lower, has_upper, has_digit, has_special])
    
    if complexity_count < 3:
        return False, "Le mot de passe doit contenir au moins 3 types de caractères (minuscules, majuscules, chiffres, symboles)"
    
    return True, "Mot de passe valide"


def sanitize_text_input(text: str) -> str:
    """Nettoyer une entrée texte des caractères dangereux"""
    if not text:
        return ""
    
    # Supprimer les caractères de contrôle
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    
    # Limiter la longueur
    text = text[:1000]
    
    return text.strip()


def validate_question_content(prompt: str, answer: str) -> tuple[bool, str]:
    """Valider le contenu d'une question préparée"""
    if not prompt or not prompt.strip():
        return False, "La question ne peut pas être vide"
    
    if not answer or not answer.strip():
        return False, "La réponse ne peut pas être vide"
    
    if len(prompt.strip()) > 1000:
        return False, "La question est trop longue (maximum 1000 caractères)"
    
    if len(answer.strip()) > 255:
        return False, "La réponse est trop longue (maximum 255 caractères)"
    
    # Vérifier les caractères dangereux
    for content in [prompt, answer]:
        if not validate_goals(content):  # Réutilise la validation des objectifs
            return False, "Contenu invalide détecté"
    
    return True, "Contenu valide"
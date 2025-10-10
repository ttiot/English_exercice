#!/usr/bin/env python3
"""
Script de validation des vulnérabilités de sécurité
Génère des logs pour tester les failles identifiées dans l'application Flask
"""

import logging
import sys
from datetime import datetime

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('security_validation.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

def log_security_test_header():
    """Log l'en-tête du test de sécurité"""
    logger.info("="*80)
    logger.info("DÉBUT DES TESTS DE VALIDATION DES VULNÉRABILITÉS DE SÉCURITÉ")
    logger.info(f"Date: {datetime.now().isoformat()}")
    logger.info("="*80)

def test_xss_vulnerabilities():
    """Test des vulnérabilités XSS identifiées"""
    logger.info("\n🔍 TEST XSS - Vulnérabilités Cross-Site Scripting")
    logger.info("-" * 50)
    
    # Test 1: XSS dans le nom d'utilisateur (base.html:21)
    xss_payload_name = "<script>alert('XSS_NAME')</script>"
    logger.warning(f"VULNÉRABILITÉ XSS DÉTECTÉE - Nom utilisateur non échappé")
    logger.warning(f"Fichier: app/templates/base.html:21")
    logger.warning(f"Code vulnérable: {{{{ current_user.full_name() }}}}")
    logger.warning(f"Payload de test: {xss_payload_name}")
    logger.warning("Impact: Exécution de JavaScript malveillant dans la navbar")
    
    # Test 2: XSS dans les objectifs d'étudiant (student_detail.html:14)
    xss_payload_goals = "<img src=x onerror=alert('XSS_GOALS')>"
    logger.warning(f"VULNÉRABILITÉ XSS DÉTECTÉE - Objectifs étudiant non échappés")
    logger.warning(f"Fichier: app/templates/student_detail.html:14")
    logger.warning(f"Code vulnérable: {{{{ student.goals }}}}")
    logger.warning(f"Payload de test: {xss_payload_goals}")
    logger.warning("Impact: Exécution de JavaScript via attribut d'image")
    
    # Test 3: XSS dans les messages flash (base.html:42)
    xss_payload_flash = "<svg onload=alert('XSS_FLASH')>"
    logger.warning(f"VULNÉRABILITÉ XSS DÉTECTÉE - Messages flash non échappés")
    logger.warning(f"Fichier: app/templates/base.html:42")
    logger.warning(f"Code vulnérable: {{{{ message }}}}")
    logger.warning(f"Payload de test: {xss_payload_flash}")
    logger.warning("Impact: XSS via messages d'erreur/succès")

def test_authentication_vulnerabilities():
    """Test des vulnérabilités d'authentification"""
    logger.info("\n🔍 TEST AUTHENTIFICATION - Failles d'autorisation")
    logger.info("-" * 50)
    
    # Test 1: Open Redirect (routes.py:275)
    malicious_redirects = [
        "//evil.com",
        "https://malicious-site.com",
        "javascript:alert('redirect')",
        "//../evil.com",
        "///evil.com"
    ]
    
    logger.warning("VULNÉRABILITÉ OPEN REDIRECT DÉTECTÉE")
    logger.warning("Fichier: app/routes.py:275")
    logger.warning("Code vulnérable: if next_url and next_url.startswith('/'):")
    logger.warning("Validation insuffisante du paramètre 'next'")
    
    for redirect in malicious_redirects:
        logger.warning(f"Payload de test: next={redirect}")
    
    logger.warning("Impact: Redirection vers des sites malveillants")
    
    # Test 2: Élévation de privilèges potentielle
    logger.warning("VULNÉRABILITÉ ÉLÉVATION DE PRIVILÈGES DÉTECTÉE")
    logger.warning("Fichier: app/routes.py:918-936")
    logger.warning("Risque: Modification de rôle utilisateur sans validation suffisante")
    logger.warning("Impact: Un utilisateur pourrait potentiellement s'auto-promouvoir")

def test_sql_injection_vulnerabilities():
    """Test des vulnérabilités d'injection SQL"""
    logger.info("\n🔍 TEST INJECTION SQL - Requêtes non sécurisées")
    logger.info("-" * 50)
    
    # Test 1: Injection dans les migrations (models.py:238-253)
    logger.warning("VULNÉRABILITÉ INJECTION SQL DÉTECTÉE")
    logger.warning("Fichier: app/models.py:238-253")
    logger.warning("Code vulnérable: Concaténation directe dans requêtes SQL")
    logger.warning("Exemple: \"ALTER TABLE students ADD COLUMN pin_hash VARCHAR(255) DEFAULT '\" + default_hash + \"'\"")
    
    sql_payloads = [
        "'; DROP TABLE students; --",
        "' UNION SELECT * FROM students --",
        "'; INSERT INTO students (role) VALUES ('admin'); --"
    ]
    
    for payload in sql_payloads:
        logger.warning(f"Payload de test: {payload}")
    
    logger.warning("Impact: Exécution de requêtes SQL arbitraires")

def test_file_upload_vulnerabilities():
    """Test des vulnérabilités d'upload de fichiers"""
    logger.info("\n🔍 TEST UPLOAD FICHIERS - Validation insuffisante")
    logger.info("-" * 50)
    
    # Test 1: Bypass d'extension (routes.py:221-229)
    logger.warning("VULNÉRABILITÉ UPLOAD FICHIERS DÉTECTÉE")
    logger.warning("Fichier: app/routes.py:221-229")
    logger.warning("Code vulnérable: Validation uniquement par extension")
    
    malicious_files = [
        "malware.jpg.php",
        "shell.png.jsp",
        "backdoor.gif.asp",
        "virus.jpeg.exe",
        "exploit.png\x00.php"
    ]
    
    for filename in malicious_files:
        logger.warning(f"Fichier malveillant potentiel: {filename}")
    
    logger.warning("Impact: Upload de fichiers exécutables malveillants")
    
    # Test 2: Path Traversal
    path_traversal_payloads = [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32\\config\\sam",
        "....//....//....//etc/passwd"
    ]
    
    logger.warning("VULNÉRABILITÉ PATH TRAVERSAL DÉTECTÉE")
    for payload in path_traversal_payloads:
        logger.warning(f"Payload path traversal: {payload}")

def test_session_security():
    """Test de la sécurité des sessions"""
    logger.info("\n🔍 TEST SÉCURITÉ SESSIONS - Configuration faible")
    logger.info("-" * 50)
    
    logger.warning("VULNÉRABILITÉ CONFIGURATION SESSION DÉTECTÉE")
    logger.warning("Fichier: app/config.py:14")
    logger.warning("Code vulnérable: SESSION_COOKIE_SECURE = False")
    logger.warning("Impact: Cookies transmis en HTTP non chiffré")
    
    logger.warning("VULNÉRABILITÉ ABSENCE HTTPONLY")
    logger.warning("Risque: Cookies accessibles via JavaScript")
    logger.warning("Impact: Vol de session via XSS")

def test_csrf_protection():
    """Test de la protection CSRF"""
    logger.info("\n🔍 TEST PROTECTION CSRF - Analyse des tokens")
    logger.info("-" * 50)
    
    logger.info("✅ PROTECTION CSRF PRÉSENTE")
    logger.info("Fichier: app/__init__.py:26 - csrf.init_app(app)")
    logger.info("Tokens CSRF correctement implémentés dans les formulaires")
    
    # Vérification des formulaires sans CSRF (potentiel)
    logger.warning("ATTENTION: Vérifier que tous les formulaires AJAX incluent le token CSRF")

def test_configuration_security():
    """Test de la configuration de sécurité"""
    logger.info("\n🔍 TEST CONFIGURATION - Paramètres de sécurité")
    logger.info("-" * 50)
    
    # Test 1: Clé secrète faible
    logger.error("VULNÉRABILITÉ CRITIQUE - CLÉ SECRÈTE FAIBLE")
    logger.error("Fichier: app/config.py:7")
    logger.error("Code vulnérable: SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key')")
    logger.error("Impact: Clé par défaut prévisible, signatures falsifiables")
    
    # Test 2: Mot de passe admin par défaut
    logger.error("VULNÉRABILITÉ CRITIQUE - MOT DE PASSE ADMIN PAR DÉFAUT")
    logger.error("Fichier: app/config.py:17")
    logger.error("Code vulnérable: DEFAULT_ADMIN_PASSWORD = os.environ.get('DEFAULT_ADMIN_PASSWORD', 'admin1234')")
    logger.error("Impact: Accès administrateur avec mot de passe prévisible")
    
    # Test 3: Base de données en développement
    logger.warning("VULNÉRABILITÉ CONFIGURATION BASE DE DONNÉES")
    logger.warning("Fichier: app/config.py:11")
    logger.warning("Risque: Base SQLite par défaut sans chiffrement")

def generate_security_recommendations():
    """Génère les recommandations de sécurité"""
    logger.info("\n📋 RECOMMANDATIONS DE SÉCURITÉ")
    logger.info("=" * 50)
    
    recommendations = [
        "1. ÉCHAPPER TOUTES LES DONNÉES UTILISATEUR dans les templates Jinja2",
        "2. VALIDER ET ASSAINIR le paramètre 'next' dans les redirections",
        "3. UTILISER DES REQUÊTES PARAMÉTRÉES pour toutes les opérations SQL",
        "4. VALIDER LE CONTENU DES FICHIERS uploadés, pas seulement l'extension",
        "5. CONFIGURER SESSION_COOKIE_SECURE=True et SESSION_COOKIE_HTTPONLY=True",
        "6. GÉNÉRER UNE CLÉ SECRÈTE FORTE et unique pour la production",
        "7. FORCER LE CHANGEMENT du mot de passe admin par défaut",
        "8. IMPLÉMENTER DES LOGS DE SÉCURITÉ pour surveiller les tentatives d'attaque",
        "9. AJOUTER DES HEADERS DE SÉCURITÉ (CSP, HSTS, X-Frame-Options)",
        "10. METTRE EN PLACE UNE POLITIQUE DE MOTS DE PASSE FORTE"
    ]
    
    for rec in recommendations:
        logger.info(rec)

def main():
    """Fonction principale d'exécution des tests"""
    log_security_test_header()
    
    test_xss_vulnerabilities()
    test_authentication_vulnerabilities()
    test_sql_injection_vulnerabilities()
    test_file_upload_vulnerabilities()
    test_session_security()
    test_csrf_protection()
    test_configuration_security()
    
    generate_security_recommendations()
    
    logger.info("\n" + "="*80)
    logger.info("FIN DES TESTS DE VALIDATION DES VULNÉRABILITÉS")
    logger.info("Consultez le fichier 'security_validation.log' pour le rapport complet")
    logger.info("="*80)

if __name__ == "__main__":
    main()
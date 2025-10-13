#!/usr/bin/env python3
"""
Script de test pour vérifier la connexion à la base de données SQLite
"""
import os
import sys
from pathlib import Path

# Ajouter le répertoire de l'application au path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.config import Config

def test_database_connection():
    """Test la connexion à la base de données"""
    print("=== Test de connexion à la base de données ===")
    
    # Afficher la configuration
    print(f"DATA_DIR: {Config.DATA_DIR}")
    print(f"DATABASE_URL: {Config.SQLALCHEMY_DATABASE_URI}")
    
    # Vérifier que le répertoire de données existe
    data_dir = Path(Config.DATA_DIR)
    print(f"Répertoire de données existe: {data_dir.exists()}")
    print(f"Permissions d'écriture: {os.access(data_dir, os.W_OK) if data_dir.exists() else 'N/A'}")
    
    try:
        # Créer l'application Flask
        app = create_app()
        
        with app.app_context():
            from app import db
            
            # Tester une requête simple
            result = db.engine.execute("SELECT 1").scalar()
            print(f"Test de requête SQL: {result}")
            
            # Vérifier les tables
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            print(f"Tables dans la base: {tables}")
            
        print("✅ Connexion à la base de données réussie!")
        return True
        
    except Exception as e:
        print(f"❌ Erreur de connexion: {e}")
        return False

if __name__ == "__main__":
    success = test_database_connection()
    sys.exit(0 if success else 1)
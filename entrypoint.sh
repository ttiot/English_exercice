#!/bin/bash
set -e

# Créer le répertoire /data s'il n'existe pas
mkdir -p /data
mkdir -p /data/uploads

# S'assurer que l'utilisateur appuser peut écrire dans /data
# Ceci est nécessaire car le volume monté peut avoir des permissions différentes
if [ -w /data ]; then
    echo "Permissions /data OK"
else
    echo "Attention: Permissions /data insuffisantes"
    # Essayer de corriger les permissions si possible
    chmod 755 /data 2>/dev/null || true
    chmod 755 /data/uploads 2>/dev/null || true
fi

# Lancer l'application
exec "$@"
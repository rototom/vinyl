#!/bin/bash

# Start-Script für Vinyl Digitalizer
# Aktiviert die virtuelle Umgebung und startet den Server

set -e

# Prüfe ob virtuelle Umgebung existiert
if [ ! -d "venv" ]; then
    echo "❌ Virtuelle Umgebung nicht gefunden!"
    echo "Bitte führe zuerst ./setup.sh aus"
    exit 1
fi

# Aktiviere virtuelle Umgebung
source venv/bin/activate

# Wechsle ins Backend-Verzeichnis
cd backend

# Starte Server
echo "🚀 Starte Vinyl Digitalizer Server auf Port 8045..."
python main.py


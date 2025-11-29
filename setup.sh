#!/bin/bash

# Setup-Script für Vinyl Digitalizer
# Erstellt eine virtuelle Umgebung und installiert alle Abhängigkeiten

set -e

echo "🎵 Vinyl Digitalizer Setup"
echo "=========================="
echo ""

# Prüfe ob Python 3 installiert ist
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 ist nicht installiert!"
    exit 1
fi

echo "✓ Python 3 gefunden: $(python3 --version)"
echo ""

# Erstelle virtuelle Umgebung
if [ ! -d "venv" ]; then
    echo "📦 Erstelle virtuelle Umgebung..."
    python3 -m venv venv
    echo "✓ Virtuelle Umgebung erstellt"
else
    echo "✓ Virtuelle Umgebung existiert bereits"
fi

echo ""

# Aktiviere virtuelle Umgebung
echo "🔧 Aktiviere virtuelle Umgebung..."
source venv/bin/activate

# Upgrade pip
echo "⬆️  Aktualisiere pip..."
pip install --upgrade pip

echo ""

# Installiere Python-Abhängigkeiten
echo "📥 Installiere Python-Abhängigkeiten..."
cd backend
pip install -r requirements.txt

echo ""
echo "✅ Setup abgeschlossen!"
echo ""
echo "Um den Server zu starten:"
echo "  source venv/bin/activate"
echo "  cd backend"
echo "  python main.py"
echo ""


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

# Prüfe und installiere System-Abhängigkeiten
echo "🔍 Prüfe System-Abhängigkeiten..."
MISSING_DEPS=()

# Prüfe ob portaudio-dev installiert ist
if ! pkg-config --exists portaudio-2.0 2>/dev/null && [ ! -f /usr/include/portaudio.h ] && [ ! -f /usr/local/include/portaudio.h ]; then
    MISSING_DEPS+=("portaudio19-dev")
fi

# Prüfe ob libsndfile installiert ist
if ! pkg-config --exists sndfile 2>/dev/null && [ ! -f /usr/include/sndfile.h ] && [ ! -f /usr/local/include/sndfile.h ]; then
    MISSING_DEPS+=("libsndfile1-dev")
fi

# Prüfe ob libsamplerate installiert ist
if ! pkg-config --exists samplerate 2>/dev/null && [ ! -f /usr/include/samplerate.h ] && [ ! -f /usr/local/include/samplerate.h ]; then
    MISSING_DEPS+=("libsamplerate0-dev")
fi

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo "⚠️  Fehlende System-Abhängigkeiten gefunden:"
    for dep in "${MISSING_DEPS[@]}"; do
        echo "   - $dep"
    done
    echo ""
    echo "Bitte installiere diese mit:"
    echo "  sudo apt-get update"
    echo "  sudo apt-get install ${MISSING_DEPS[*]} python3-venv python3-pip"
    echo ""
    read -p "Möchtest du diese jetzt installieren? (j/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Jj]$ ]]; then
        echo "📦 Installiere System-Abhängigkeiten..."
        sudo apt-get update
        sudo apt-get install -y "${MISSING_DEPS[@]}" python3-venv python3-pip
        echo "✓ System-Abhängigkeiten installiert"
    else
        echo "❌ Setup abgebrochen. Bitte installiere die Abhängigkeiten manuell."
        exit 1
    fi
else
    echo "✓ Alle System-Abhängigkeiten vorhanden"
fi

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

# Upgrade pip, setuptools und wheel
echo "⬆️  Aktualisiere pip, setuptools und wheel..."
pip install --upgrade pip setuptools wheel

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


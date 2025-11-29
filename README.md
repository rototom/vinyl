# 🎵 Vinyl Digitalizer

Professionelle Schallplatten-Digitalisierungs-Software mit Webinterface für Raspberry Pi.

## Features

- 🎤 Hochwertige FLAC-Aufnahmen (44.1 kHz Stereo)
- ✂️ Automatisches Track-Splitting basierend auf Pausen-Erkennung
- 🏷️ Metadaten-Tagging (Titel, Interpret, Album, etc.)
- 📊 Live Audio-Level Visualisierung
- 🎨 Modernes, responsives Webinterface

## Installation

### Voraussetzungen

- Raspberry Pi mit Linux
- Python 3.8+
- Phono-Audio Interface angeschlossen
- Plattenspieler angeschlossen

### Setup

**Automatisch mit Setup-Script (empfohlen):**

```bash
# Repository klonen
git clone https://github.com/rototom/vinyl.git
cd vinyl

# Setup-Script ausführen (installiert automatisch System-Abhängigkeiten)
./setup.sh
```

**Manuell:**

```bash
# Repository klonen
git clone https://github.com/rototom/vinyl.git
cd vinyl

# System-Abhängigkeiten installieren (Raspberry Pi)
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip portaudio19-dev libsndfile1-dev libsamplerate0-dev

# Virtuelle Umgebung erstellen und aktivieren
python3 -m venv venv
source venv/bin/activate

# Build-Tools installieren
pip install --upgrade pip setuptools wheel

# Python-Abhängigkeiten installieren
cd backend
pip install -r requirements.txt

# Server starten
cd ..
./start.sh
```

**Hinweis:** Bei jedem Start muss die virtuelle Umgebung aktiviert werden:
```bash
source venv/bin/activate
cd backend
python main.py
```

## Verwendung

1. Öffne `http://raspberrypi-ip:8045` im Browser
2. Starte die Aufnahme
3. Stoppe die Aufnahme wenn die Platte fertig ist
4. Klicke auf "Tracks automatisch splitten"
5. Bearbeite die Metadaten für jeden Track
6. Speichere die getaggten FLAC-Dateien

## Projektstruktur

```
vinyl/
├── backend/          # FastAPI Backend
│   ├── main.py       # Hauptserver
│   ├── audio_recorder.py    # Audio-Aufnahme
│   ├── track_splitter.py    # Track-Splitting
│   ├── tagger.py     # Metadaten-Tagging
│   └── requirements.txt
├── frontend/         # Webinterface
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── recordings/       # Aufgenommene Dateien
├── venv/            # Virtuelle Umgebung (wird erstellt)
├── setup.sh         # Setup-Script
└── start.sh         # Start-Script
```

## Schnellstart

```bash
# Setup einmalig ausführen
./setup.sh

# Server starten
./start.sh
```

## API Endpunkte

- `GET /` - Webinterface
- `GET /api/status` - Status der Aufnahme
- `POST /api/start-recording` - Aufnahme starten
- `POST /api/stop-recording` - Aufnahme stoppen
- `GET /api/recordings` - Liste aller Aufnahmen
- `POST /api/split-tracks` - Tracks automatisch splitten
- `POST /api/tag-track` - Metadaten hinzufügen
- `DELETE /api/delete/{filename}` - Aufnahme löschen
- `WS /ws` - WebSocket für Audio-Level Updates

## Technologie-Stack

- **Backend**: FastAPI, PyAudio, librosa, mutagen
- **Frontend**: Vanilla JavaScript, Tailwind CSS
- **Audio**: FLAC Format, 44.1 kHz, Stereo

## Lizenz

MIT


# 🎵 Vinyl Digitalizer

Professionelle Schallplatten-Digitalisierungs-Software mit Webinterface für Raspberry Pi.

## Features

- 🎤 Hochwertige FLAC-Aufnahmen (44.1 kHz Stereo, konfigurierbar)
- ✂️ Automatisches Track-Splitting basierend auf Pausen-Erkennung
- 🏷️ Automatisches Metadaten-Tagging via MusicBrainz API
- 📊 Live Audio-Level Visualisierung mit Waveform
- 🎨 Modernes, responsives Webinterface mit Tab-Navigation
- 🔄 **Robuste Aufnahme**: Läuft weiter auch bei Browser-Reload oder Neustart
- 🛑 **Auto-Stop**: Automatisches Stoppen nach konfigurierbarer Stille-Dauer
- 📀 **Album-Verwaltung**: Übersichtliche Sammlung mit Cover-Art
- ⬇️ **Download-Funktionen**: Einzelne Tracks oder komplette Alben als ZIP
- 🎛️ **Flexible Einstellungen**: Audio-Gerät, Sample-Rate, Kanäle, Benennung
- 🔌 **ALSA-Unterstützung**: Direkte ALSA-Integration als Fallback

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

1. Öffne `http://raspberrypi-ip:8045` im Browser (oder `http://plattenspieler.local:8045` wenn Hostname konfiguriert)
2. **Aufnahme starten**: Klicke auf "Aufnahme starten" - die Aufnahme läuft serverseitig weiter, auch wenn der Browser geschlossen wird
3. **Aufnahme stoppen**: Klicke auf "Aufnahme stoppen" wenn die Platte fertig ist (oder nutze Auto-Stop nach Stille)
4. **Tracks splitten**: Wähle die Aufnahme aus und klicke auf "Tracks automatisch splitten"
5. **Metadaten hinzufügen**: Suche nach dem Album in MusicBrainz und wende die Metadaten automatisch an
6. **Alben verwalten**: Wechsle zum Tab "Alben-Sammlung" für Übersicht und Downloads
7. **Einstellungen anpassen**: Im Tab "Einstellungen" kannst du Audio-Gerät, Sample-Rate, Auto-Stop und mehr konfigurieren

## Projektstruktur

```
vinyl/
├── backend/              # FastAPI Backend
│   ├── main.py          # Hauptserver
│   ├── audio_recorder.py    # PyAudio-basierte Audio-Aufnahme
│   ├── alsa_recorder.py     # ALSA-basierte Audio-Aufnahme (Fallback)
│   ├── track_splitter.py    # Track-Splitting basierend auf Stille-Erkennung
│   ├── tagger.py         # Metadaten-Tagging (FLAC)
│   ├── metadata_search.py # MusicBrainz API Integration
│   ├── config.py         # Konfigurationsverwaltung
│   ├── recording_state.py # Persistenter Aufnahme-Status
│   └── requirements.txt
├── frontend/             # Webinterface
│   ├── index.html        # Haupt-HTML
│   ├── app.js           # Frontend-Logik
│   ├── styles.css       # Styles (falls vorhanden)
│   └── favicon.svg      # Favicon
├── recordings/           # Aufgenommene Dateien (FLAC)
├── config/               # Konfigurationsdateien
│   ├── settings.json     # Einstellungen (wird erstellt)
│   └── recording_state.json  # Aufnahme-Status (wird erstellt)
├── venv/                 # Virtuelle Umgebung (wird erstellt)
├── setup.sh              # Setup-Script
└── start.sh               # Start-Script
```

## Schnellstart

```bash
# Setup einmalig ausführen
./setup.sh

# Server starten
./start.sh
```

## API Endpunkte

### Aufnahme
- `GET /api/status` - Status der Aufnahme (inkl. Geräte-Info)
- `POST /api/start-recording` - Aufnahme starten
- `POST /api/stop-recording` - Aufnahme stoppen

### Dateien & Tracks
- `GET /api/recordings` - Liste aller Aufnahmen
- `GET /api/tracks/{base_filename}` - Liste aller Tracks einer Aufnahme
- `GET /api/albums` - Liste aller Alben (gruppiert nach Metadaten)
- `GET /api/audio/{filename}` - Audio-Datei für Playback
- `GET /api/download/{filename}` - Download einzelner Datei
- `GET /api/download-album/{base_filename}` - Download Album als ZIP
- `GET /api/download-collection` - Download aller Alben als ZIP
- `GET /api/cover/{filename}` - Album-Cover-Art

### Verarbeitung
- `POST /api/split-tracks` - Tracks automatisch splitten
- `POST /api/search-album` - Suche nach Album in MusicBrainz
- `POST /api/auto-tag-album` - Automatisches Tagging mit MusicBrainz-Daten
- `POST /api/tag-track` - Manuelles Metadaten-Tagging

### Verwaltung
- `DELETE /api/delete/{filename}` - Einzelne Datei löschen
- `DELETE /api/delete-album/{base_filename}` - Komplettes Album löschen

### Einstellungen
- `GET /api/settings` - Alle Einstellungen abrufen
- `POST /api/settings` - Einstellungen aktualisieren

### WebSocket
- `WS /ws` - WebSocket für Live Audio-Level Updates

## Technologie-Stack

### Backend
- **Framework**: FastAPI (Python)
- **Audio-Aufnahme**: PyAudio, ALSA (arecord)
- **Audio-Verarbeitung**: librosa, pydub, soundfile
- **Metadaten**: mutagen (FLAC-Tagging)
- **API-Integration**: MusicBrainz API, Cover Art Archive
- **Konfiguration**: JSON-basierte Einstellungen

### Frontend
- **Sprache**: Vanilla JavaScript (ES6+)
- **Styling**: Tailwind CSS (CDN)
- **Visualisierung**: HTML5 Canvas (Waveform)
- **Kommunikation**: WebSocket, Fetch API

### Audio-Format
- **Format**: FLAC (Free Lossless Audio Codec)
- **Sample-Rate**: Konfigurierbar (Standard: 44.1 kHz)
- **Kanäle**: Mono oder Stereo (konfigurierbar)
- **Qualität**: 24-bit PCM

## Besondere Features

### Robuste Aufnahme
Die Aufnahme läuft serverseitig weiter, auch wenn:
- Der Browser geschlossen wird
- Die Seite neu geladen wird
- Die Netzwerkverbindung abbricht

Der Status wird persistent gespeichert und beim Neustart wiederhergestellt.

### Auto-Stop
Konfigurierbare automatische Beendigung der Aufnahme nach einer bestimmten Dauer ohne Audio-Signal (Stille-Erkennung).

### MusicBrainz-Integration
Automatische Suche und Anwendung von Metadaten aus der MusicBrainz-Datenbank, inklusive Cover-Art.

## Lizenz

MIT


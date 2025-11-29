from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import uvicorn
import os
import json
from pathlib import Path
from datetime import datetime
from audio_recorder import AudioRecorder
from alsa_recorder import ALSARecorder
from track_splitter import TrackSplitter
from tagger import AudioTagger
from metadata_search import MetadataSearcher
from config import Config
from recording_state import RecordingState
import asyncio

app = FastAPI(title="Vinyl Digitalizer")

# CORS für Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Projekt-Root-Verzeichnis bestimmen (ein Verzeichnis über backend/)
BASE_DIR = Path(__file__).parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
RECORDINGS_DIR = BASE_DIR / "recordings"
CONFIG_DIR = BASE_DIR / "config"

# Verzeichnisse erstellen
RECORDINGS_DIR.mkdir(exist_ok=True)
CONFIG_DIR.mkdir(exist_ok=True)

# Konfiguration laden
config = Config(CONFIG_DIR / "settings.json")
auto_stop_silence_duration = config.get("recording.auto_stop_silence_duration", 0.0)  # 0.0 = deaktiviert

# Aufnahme-Status laden
recording_state = RecordingState(CONFIG_DIR / "recording_state.json")

# Frontend statisch servieren
try:
    if FRONTEND_DIR.exists():
        # Serviere statische Dateien (app.js, styles.css) direkt
        app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
    else:
        print(f"Warnung: Frontend-Verzeichnis nicht gefunden: {FRONTEND_DIR}")
except Exception as e:
    print(f"Warnung: Frontend-Verzeichnis nicht gefunden: {e}")

# Explizite Routen für statische Dateien - MÜSSEN VOR DER ROOT-ROUTE KOMMEN!
@app.get("/app.js")
async def serve_app_js():
    """Serviere JavaScript-Datei"""
    js_path = FRONTEND_DIR / "app.js"
    if not js_path.exists():
        raise FileNotFoundError(f"app.js nicht gefunden: {js_path}")
    
    try:
        # Lese Datei als Bytes, dann als UTF-8
        content_bytes = js_path.read_bytes()
        content = content_bytes.decode('utf-8')
        
        # Prüfe dass die Datei korrekt beginnt
        if not content.startswith('//'):
            print(f"⚠️  WARNUNG: app.js beginnt nicht mit Kommentar! Beginnt mit: {repr(content[:50])}")
        
        print(f"✓ Serviere app.js ({len(content)} Zeichen, {len(content_bytes)} Bytes)")
        
        # Verwende FileResponse für bessere Performance
        return FileResponse(
            str(js_path),
            media_type="application/javascript; charset=utf-8",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "X-Content-Type-Options": "nosniff",
                "Content-Length": str(len(content_bytes))
            }
        )
    except Exception as e:
        print(f"Fehler beim Lesen von app.js: {e}")
        import traceback
        traceback.print_exc()
        raise

@app.get("/styles.css")
async def serve_styles_css():
    css_path = FRONTEND_DIR / "styles.css"
    if css_path.exists():
        return FileResponse(str(css_path), media_type="text/css")
    raise FileNotFoundError("styles.css nicht gefunden")

@app.get("/favicon.svg")
async def serve_favicon():
    """Serviere Favicon"""
    favicon_path = FRONTEND_DIR / "favicon.svg"
    if favicon_path.exists():
        return FileResponse(str(favicon_path), media_type="image/svg+xml")
    from fastapi.responses import Response
    return Response(status_code=204)

@app.get("/favicon.ico")
async def serve_favicon_ico():
    """Serviere Favicon als ICO (Fallback)"""
    favicon_path = FRONTEND_DIR / "favicon.svg"
    if favicon_path.exists():
        return FileResponse(str(favicon_path), media_type="image/svg+xml")
    from fastapi.responses import Response
    return Response(status_code=204)

# Globale Instanzen - mit Fehlerbehandlung
recorder = None
use_alsa = False

try:
    device_index = config.get("audio.device_index")
    sample_rate = config.get("audio.sample_rate", 44100)
    channels = config.get("audio.channels", 2)
    chunk_size = config.get("audio.chunk_size", 4096)
    
    # Versuche PyAudio-Recorder
    pyrecorder = AudioRecorder(
        device_index=device_index,
        sample_rate=sample_rate,
        channels=channels,
        chunk=chunk_size
    )
    
    # Prüfe ob Input-Geräte verfügbar sind
    devices = pyrecorder.get_audio_devices()
    if devices and len(devices) > 0:
        recorder = pyrecorder
        recorder.silence_threshold_db = config.get("recording.silence_threshold_db", -40)
        recorder.auto_stop_silence_seconds = auto_stop_silence_duration
        print("✓ PyAudio-Recorder initialisiert")
    else:
        print("⚠️  PyAudio findet keine Input-Geräte, verwende ALSA-Recorder")
        use_alsa = True
        
except Exception as e:
    print(f"Warnung: AudioRecorder konnte nicht initialisiert werden: {e}")
    use_alsa = True

# Falls PyAudio nicht funktioniert, verwende ALSA
if use_alsa or recorder is None:
    try:
        alsa_device = config.get("audio.alsa_device", "hw:1,0")
        sample_rate = config.get("audio.sample_rate", 44100)
        channels = config.get("audio.channels", 2)
        recorder = ALSARecorder(
            alsa_device=alsa_device,
            sample_rate=sample_rate,
            channels=channels
        )
        recorder.auto_stop_silence_seconds = auto_stop_silence_duration
        recorder.silence_threshold_db = config.get("recording.silence_threshold_db", -40)
        print(f"✓ ALSA-Recorder initialisiert mit Gerät: {alsa_device}")
    except Exception as e:
        print(f"Fehler: ALSA-Recorder konnte nicht initialisiert werden: {e}")
        recorder = None

# TrackSplitter mit Konfiguration initialisieren
splitter = TrackSplitter()
splitter.silence_threshold = config.get("recording.silence_threshold_db", -40)
splitter.min_silence_duration = config.get("recording.min_silence_duration", 2.0)
splitter.min_track_duration = config.get("recording.min_track_duration", 10.0)

tagger = AudioTagger()
metadata_searcher = MetadataSearcher()

# Prüfe beim Start ob eine Aufnahme läuft und stelle sie wieder her
def restore_recording_state():
    """Stelle Aufnahme-Status wieder her falls eine Aufnahme läuft"""
    if recording_state.is_recording():
        filename = recording_state.get_filename()
        if filename:
            # Prüfe ob die Aufnahme-Datei existiert
            recording_path = RECORDINGS_DIR / filename
            recorder_type = recording_state.state.get("recorder_type")
            
            if recorder_type == "alsa":
                # Für ALSA: Prüfe ob arecord-Prozess läuft
                import subprocess
                try:
                    # Prüfe ob arecord-Prozess läuft (suche nach arecord-Prozessen)
                    result = subprocess.run(
                        ['pgrep', '-f', 'arecord'],
                        capture_output=True,
                        text=True,
                        timeout=1
                    )
                    if result.returncode == 0:
                        # Prüfe ob Datei noch geschrieben wird (Dateigröße ändert sich)
                        if recording_path.exists():
                            import time
                            size1 = recording_path.stat().st_size
                            time.sleep(0.5)
                            if recording_path.exists():
                                size2 = recording_path.stat().st_size
                                if size2 > size1:
                                    print(f"✓ Aufnahme läuft noch (ALSA): {filename}")
                                    return True
                except Exception as e:
                    print(f"Fehler beim Prüfen der ALSA-Aufnahme: {e}")
            else:
                # Für PyAudio: Prüfe ob Recorder noch läuft
                if recorder and recorder.is_recording():
                    print(f"✓ Aufnahme läuft noch (PyAudio): {filename}")
                    return True
            
            # Aufnahme läuft nicht mehr - Status zurücksetzen
            print(f"⚠️  Aufnahme-Status gefunden, aber Aufnahme läuft nicht mehr: {filename}")
            recording_state.stop_recording()
    return False

# Stelle Aufnahme-Status wieder her
restore_recording_state()

@app.get("/")
async def read_root():
    """Serviere HTML-Datei - MUSS NACH ALLEN ANDEREN ROUTEN KOMMEN!"""
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise FileNotFoundError(f"Frontend-Datei nicht gefunden: {index_path}")
    
    # Lese Datei und prüfe dass sie korrekt ist
    try:
        content = index_path.read_text(encoding='utf-8')
        if not content.startswith('<!DOCTYPE'):
            print(f"⚠️  WARNUNG: HTML-Datei beginnt nicht mit <!DOCTYPE! Beginnt mit: {repr(content[:50])}")
            raise ValueError("HTML-Datei ist nicht korrekt")
        
        print(f"✓ Serviere index.html ({len(content)} Zeichen)")
        
        # Verwende Response mit explizitem Content-Type
        from fastapi.responses import Response
        return Response(
            content=content,
            media_type="text/html; charset=utf-8",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Content-Type": "text/html; charset=utf-8",
                "X-Content-Type-Options": "nosniff"
            }
        )
    except Exception as e:
        print(f"Fehler beim Lesen von index.html: {e}")
        import traceback
        traceback.print_exc()
        raise

@app.get("/api/status")
async def get_status():
    if recorder is None:
        return {
            "recording": False,
            "devices": [],
            "alsa_devices": [],
            "use_alsa": False,
            "error": "AudioRecorder nicht verfügbar",
            "recording_filename": None
        }
    
    # Prüfe ob ALSA-Recorder verwendet wird
    is_alsa = isinstance(recorder, ALSARecorder)
    
    # PyAudio-Geräte (nur wenn PyAudio-Recorder)
    pyaudio_devices = []
    if not is_alsa:
        pyaudio_devices = recorder.get_audio_devices()
    
    # ALSA-Geräte
    alsa_devices = Config.get_alsa_devices()
    if is_alsa:
        alsa_devices = recorder.get_alsa_devices()
    
    current_device = None
    if is_alsa:
        current_device = recorder.alsa_device
    else:
        current_device = recorder.device_index
    
    # Prüfe sowohl Recorder-Status als auch persistenten Status
    is_recording = recorder.is_recording() or recording_state.is_recording()
    recording_filename = recording_state.get_filename() if is_recording else None
    
    return {
        "recording": is_recording,
        "devices": pyaudio_devices,
        "alsa_devices": alsa_devices,
        "use_alsa": is_alsa,
        "current_device": current_device,
        "recording_filename": recording_filename
    }

@app.post("/api/start-recording")
async def start_recording():
    if recorder is None:
        return JSONResponse(
            {"error": "AudioRecorder nicht verfügbar"}, 
            status_code=503
        )
    if recorder.is_recording():
        return JSONResponse(
            {"error": "Aufnahme läuft bereits"}, 
            status_code=400
        )
    
    # Generiere Dateinamen basierend auf Konfiguration
    naming_pattern = config.get("naming.pattern", "{date}")
    use_timestamp = config.get("naming.use_timestamp", True)
    timestamp_format = config.get("naming.timestamp_format", "%Y%m%d_%H%M%S")
    
    if use_timestamp:
        timestamp = datetime.now().strftime(timestamp_format)
        filename_template = f"recording_{timestamp}.wav"
    else:
        filename_template = naming_pattern.format(
            date=datetime.now().strftime("%Y%m%d"),
            time=datetime.now().strftime("%H%M%S")
        ) + ".wav"
    
    filename = recorder.start_recording(RECORDINGS_DIR, filename_template)
    
    # Speichere Status persistent
    recorder_type = "alsa" if isinstance(recorder, ALSARecorder) else "pyaudio"
    device = recorder.alsa_device if isinstance(recorder, ALSARecorder) else recorder.device_index
    recording_state.start_recording(filename, recorder_type, device)
    
    return {"filename": filename, "status": "recording_started"}

@app.post("/api/stop-recording")
async def stop_recording():
    if recorder is None:
        return JSONResponse(
            {"error": "AudioRecorder nicht verfügbar"}, 
            status_code=503
        )
    if not recorder.is_recording():
        return JSONResponse(
            {"error": "Keine Aufnahme aktiv"}, 
            status_code=400
        )
    
    filename = recorder.stop_recording()
    
    # Aktualisiere persistenten Status
    recording_state.stop_recording()
    
    return {"filename": filename, "status": "recording_stopped"}

@app.get("/api/recordings")
async def list_recordings():
    """Liste alle Aufnahmen (Original-Aufnahmen, keine Tracks)"""
    recordings = []
    for file in RECORDINGS_DIR.glob("*.flac"):
        # Ignoriere Tracks (haben _track_ im Namen)
        if "_track_" not in file.name:
            recordings.append({
                "filename": file.name,
                "size": file.stat().st_size,
                "created": file.stat().st_mtime
            })
    return {"recordings": sorted(recordings, key=lambda x: x["created"], reverse=True)}

@app.get("/api/albums")
async def list_albums():
    """Gruppiere Tracks nach Album"""
    from mutagen.flac import FLAC
    albums = {}
    
    # Sammle alle Tracks
    for file in RECORDINGS_DIR.glob("*_track_*.flac"):
        try:
            audio = FLAC(str(file))
            album = audio.get('ALBUM', ['Unbekanntes Album'])[0]
            artist = audio.get('ALBUMARTIST', audio.get('ARTIST', ['Unbekannter Künstler'])[0])[0]
            album_key = f"{artist} - {album}"
            
            if album_key not in albums:
                albums[album_key] = {
                    "album": album,
                    "artist": artist,
                    "tracks": [],
                    "cover": None,
                    "year": audio.get('DATE', [None])[0],
                    "total_tracks": 0
                }
            
            track_num = int(audio.get('TRACKNUMBER', ['0'])[0].split('/')[0])
            disc_num = int(audio.get('DISCNUMBER', ['1'])[0])
            
            # Prüfe ob Cover vorhanden
            if albums[album_key]["cover"] is None and audio.pictures:
                # Extrahiere Cover - verwende Album-Key als Basis für Dateinamen
                safe_album_key = "".join(c for c in album_key if c.isalnum() or c in (' ', '-', '_')).strip().replace(' ', '_')
                cover_path = RECORDINGS_DIR / f"{safe_album_key}_cover.jpg"
                if not cover_path.exists():
                    try:
                        picture = audio.pictures[0]
                        cover_path.write_bytes(picture.data)
                    except Exception as e:
                        print(f"Fehler beim Extrahieren des Covers: {e}")
                        pass
                if cover_path.exists():
                    albums[album_key]["cover"] = f"/api/cover/{cover_path.name}"
            
            albums[album_key]["tracks"].append({
                "filename": file.name,
                "title": audio.get('TITLE', ['Unbekannt'])[0],
                "track_number": track_num,
                "disc_number": disc_num,
                "size": file.stat().st_size
            })
            
        except Exception as e:
            print(f"Fehler beim Lesen von {file}: {e}")
            continue
    
    # Sortiere Tracks innerhalb jedes Albums
    for album_key in albums:
        albums[album_key]["tracks"].sort(key=lambda x: (x["disc_number"], x["track_number"]))
        albums[album_key]["total_tracks"] = len(albums[album_key]["tracks"])
    
    return {"albums": albums}

@app.get("/api/tracks/{base_filename}")
async def list_tracks(base_filename: str):
    """Liste alle Tracks für eine Aufnahme"""
    base_name = Path(base_filename).stem.replace('_track_', '').split('_track_')[0]
    tracks = []
    
    for file in sorted(RECORDINGS_DIR.glob(f"{base_name}_track_*.flac")):
        tracks.append({
            "filename": file.name,
            "size": file.stat().st_size,
            "created": file.stat().st_mtime
        })
    
    return {"tracks": tracks}

@app.get("/api/cover/{filename}")
async def get_cover(filename: str):
    """Serviere Cover-Art"""
    filepath = RECORDINGS_DIR / filename
    if filepath.exists():
        return FileResponse(str(filepath), media_type="image/jpeg")
    return JSONResponse({"error": "Cover nicht gefunden"}, status_code=404)

@app.get("/api/download-collection")
async def download_collection():
    """Download aller Alben als ZIP"""
    import zipfile
    from mutagen.flac import FLAC
    
    # Sammle alle Alben
    albums = {}
    for file in RECORDINGS_DIR.glob("*_track_*.flac"):
        try:
            audio = FLAC(str(file))
            album = audio.get('ALBUM', ['Unbekanntes Album'])[0]
            artist = audio.get('ALBUMARTIST', audio.get('ARTIST', ['Unbekannter Künstler'])[0])[0]
            album_key = f"{artist} - {album}"
            
            if album_key not in albums:
                albums[album_key] = []
            albums[album_key].append(file)
        except:
            continue
    
    if not albums:
        return JSONResponse({"error": "Keine Alben gefunden"}, status_code=404)
    
    # Erstelle ZIP
    zip_filename = f"vinyl_collection_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    zip_path = RECORDINGS_DIR / zip_filename
    
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for album_key, files in albums.items():
                # Erstelle Ordner für jedes Album
                safe_folder = "".join(c for c in album_key if c.isalnum() or c in (' ', '-', '_')).strip()
                for file in sorted(files):
                    zipf.write(file, f"{safe_folder}/{file.name}")
        
        return FileResponse(
            str(zip_path),
            media_type="application/zip",
            filename=zip_filename,
            headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'}
        )
    except Exception as e:
        return JSONResponse({"error": f"Fehler: {e}"}, status_code=500)

@app.post("/api/split-tracks")
async def split_tracks(filename: str = Form(...)):
    filepath = RECORDINGS_DIR / filename
    if not filepath.exists():
        return JSONResponse(
            {"error": "Datei nicht gefunden"}, 
            status_code=404
        )
    
    try:
        tracks = splitter.split_audio(filepath, RECORDINGS_DIR)
        return {"tracks": tracks, "status": "success"}
    except Exception as e:
        return JSONResponse(
            {"error": str(e)}, 
            status_code=500
        )

@app.post("/api/search-album")
async def search_album(artist: str = Form(...), album: str = Form(...)):
    """Suche nach Album in MusicBrainz"""
    try:
        releases = metadata_searcher.search_album(artist, album)
        return {"releases": releases, "status": "success"}
    except Exception as e:
        return JSONResponse(
            {"error": str(e)}, 
            status_code=500
        )

@app.post("/api/auto-tag-album")
async def auto_tag_album(
    base_filename: str = Form(...),
    release_mbid: str = Form(...),
    tracks_per_side: Optional[int] = Form(None)
):
    """Automatisches Tagging eines Albums basierend auf MusicBrainz-Daten"""
    try:
        # Finde alle Tracks dieses Albums
        base_name = Path(base_filename).stem.replace('_track_', '').split('_track_')[0]
        track_files = sorted(RECORDINGS_DIR.glob(f"{base_name}_track_*.flac"))
        
        if not track_files:
            return JSONResponse(
                {"error": "Keine Tracks für dieses Album gefunden"}, 
                status_code=404
            )
        
        # Hole Release-Details von MusicBrainz
        release_url = f"{metadata_searcher.musicbrainz_base}/release/{release_mbid}"
        params = {
            "inc": "recordings+media+artist-credits",
            "fmt": "json"
        }
        import requests
        response = requests.get(release_url, params=params, headers=metadata_searcher.headers, timeout=10)
        response.raise_for_status()
        release_data = response.json()
        
        # Extrahiere Album-Informationen
        album_title = release_data.get("title", "")
        album_artist = ""
        if release_data.get("artist-credit"):
            album_artist = release_data.get("artist-credit", [{}])[0].get("name", "")
        album_date = release_data.get("date", "")[:4] if release_data.get("date") else None
        
        # Hole Cover-Art
        cover_path = None
        try:
            cover_url = f"{metadata_searcher.coverart_base}/release/{release_mbid}/front"
            cover_response = requests.get(cover_url, headers=metadata_searcher.headers, timeout=10)
            if cover_response.status_code == 200:
                cover_path = RECORDINGS_DIR / f"{base_name}_cover.jpg"
                cover_path.write_bytes(cover_response.content)
                print(f"✓ Cover-Art gespeichert: {cover_path}")
        except Exception as e:
            print(f"Fehler beim Laden des Covers: {e}")
        
        # Extrahiere Track-Informationen aus Media (alle Media zusammen)
        # Bei Multi-Disc: Alle Tracks über alle Discs hinweg
        media_tracks = []
        for medium in release_data.get("media", []):
            medium_position = medium.get("position", 1)
            # Bei Vinyl: Medium 1-2 = Disc 1, Medium 3-4 = Disc 2, etc.
            # Bei CD: Jedes Medium = 1 Disc
            is_vinyl = medium.get("format", "").lower() in ["vinyl", "12\"", "lp", ""]
            if is_vinyl:
                disc_number = (medium_position + 1) // 2
            else:
                disc_number = medium_position
            
            for track in medium.get("tracks", []):
                recording = track.get("recording", {})
                media_tracks.append({
                    "position": track.get("position", 0),
                    "title": recording.get("title", "") if recording else "",
                    "length": track.get("length", 0),
                    "medium_position": medium_position,
                    "disc_number": disc_number
                })
        
        # Sortiere Tracks nach Disc-Nummer, Medium-Position und Track-Position
        media_tracks.sort(key=lambda x: (x["disc_number"], x["medium_position"], x["position"]))
        
        print(f"Gefundene Tracks in MusicBrainz: {len(media_tracks)}")
        print(f"Tracks in Dateien: {len(track_files)}")
        
        # Tagge alle Tracks
        tagged_count = 0
        for i, track_file in enumerate(track_files):
            if i < len(media_tracks):
                track_info = media_tracks[i]
                tagger.tag_file(
                    track_file,
                    title=track_info["title"],
                    artist=album_artist,
                    album=album_title,
                    track_number=i + 1,
                    year=album_date,
                    cover_path=cover_path,
                    album_artist=album_artist,
                    disc_number=track_info.get("disc_number", 1),
                    total_tracks=len(track_files)
                )
                tagged_count += 1
            else:
                # Falls mehr Tracks als Metadaten vorhanden sind, tagge mit Platzhalter
                tagger.tag_file(
                    track_file,
                    title=f"Track {i + 1}",
                    artist=album_artist,
                    album=album_title,
                    track_number=i + 1,
                    year=album_date,
                    cover_path=cover_path,
                    album_artist=album_artist,
                    total_tracks=len(track_files)
                )
                tagged_count += 1
        
        return {
            "status": "success",
            "tagged_tracks": tagged_count,
            "album": album_title,
            "artist": album_artist
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            {"error": str(e)}, 
            status_code=500
        )

@app.post("/api/tag-track")
async def tag_track(
    filename: str = Form(...),
    title: str = Form(...),
    artist: str = Form(...),
    album: str = Form(...),
    track_number: int = Form(...)
):
    filepath = RECORDINGS_DIR / filename
    if not filepath.exists():
        return JSONResponse(
            {"error": "Datei nicht gefunden"}, 
            status_code=404
        )
    
    try:
        tagger.tag_file(
            filepath,
            title=title,
            artist=artist,
            album=album,
            track_number=track_number
        )
        return {"status": "success"}
    except Exception as e:
        return JSONResponse(
            {"error": str(e)}, 
            status_code=500
        )

@app.get("/api/audio/{filename}")
async def get_audio_file(filename: str):
    """Serviere Audio-Datei für Playback"""
    filepath = RECORDINGS_DIR / filename
    if not filepath.exists():
        return JSONResponse(
            {"error": "Datei nicht gefunden"}, 
            status_code=404
        )
    return FileResponse(
        str(filepath),
        media_type="audio/flac",
        filename=filename
    )

@app.get("/api/download/{filename}")
async def download_file(filename: str):
    """Download einzelne Audio-Datei"""
    filepath = RECORDINGS_DIR / filename
    if not filepath.exists():
        return JSONResponse(
            {"error": "Datei nicht gefunden"}, 
            status_code=404
        )
    return FileResponse(
        str(filepath),
        media_type="application/octet-stream",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

@app.get("/api/download-album/{base_filename}")
async def download_album(base_filename: str):
    """Download Album als ZIP-Datei"""
    import zipfile
    import tempfile
    
    # Finde alle Dateien die zu diesem Album gehören
    base_name = Path(base_filename).stem.replace('_track_', '').split('_track_')[0]
    album_files = []
    
    # Original-Aufnahme
    original_file = RECORDINGS_DIR / base_filename
    if original_file.exists():
        album_files.append(original_file)
    
    # Alle Tracks
    for file in RECORDINGS_DIR.glob(f"{base_name}_track_*.flac"):
        album_files.append(file)
    
    if not album_files:
        return JSONResponse(
            {"error": "Keine Dateien für Album gefunden"}, 
            status_code=404
        )
    
    # Erstelle ZIP-Datei
    zip_filename = f"{base_name}_album.zip"
    zip_path = RECORDINGS_DIR / zip_filename
    
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file in album_files:
                zipf.write(file, file.name)
        
        return FileResponse(
            str(zip_path),
            media_type="application/zip",
            filename=zip_filename,
            headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'}
        )
    except Exception as e:
        return JSONResponse(
            {"error": f"Fehler beim Erstellen der ZIP-Datei: {e}"}, 
            status_code=500
        )

@app.delete("/api/delete/{filename}")
async def delete_recording(filename: str):
    """Lösche eine Aufnahme oder einen Track"""
    filepath = RECORDINGS_DIR / filename
    if filepath.exists():
        filepath.unlink()
        return {"status": "deleted", "filename": filename}
    return JSONResponse(
        {"error": "Datei nicht gefunden"}, 
        status_code=404
    )

@app.delete("/api/delete-album/{base_filename}")
async def delete_album(base_filename: str):
    """Lösche ein komplettes Album (alle Tracks, Cover und Original-Aufnahme)"""
    # Extrahiere Basis-Namen (ohne _track_XX)
    base_name = Path(base_filename).stem
    if "_track_" in base_name:
        base_name = base_name.split("_track_")[0]
    
    deleted_files = []
    errors = []
    
    # Finde alle Tracks dieses Albums
    track_files = list(RECORDINGS_DIR.glob(f"{base_name}_track_*.flac"))
    
    # Wenn keine Tracks gefunden, versuche mit dem übergebenen Dateinamen
    if not track_files:
        # Versuche Original-Aufnahme zu finden
        possible_names = [
            base_filename,
            f"{base_name}.flac",
            f"{base_name}.wav"
        ]
        for name in possible_names:
            original_file = RECORDINGS_DIR / name
            if original_file.exists():
                track_files = [original_file]
                break
    
    # Lösche alle Tracks
    for file in track_files:
        try:
            file.unlink()
            deleted_files.append(file.name)
        except Exception as e:
            errors.append(f"Fehler beim Löschen von {file.name}: {e}")
    
    # Finde und lösche Original-Aufnahme (falls vorhanden)
    # Suche nach Dateien die nicht _track_ enthalten aber den gleichen Basis-Namen haben
    for file in RECORDINGS_DIR.glob(f"{base_name}.*"):
        if "_track_" not in file.name and file.name not in deleted_files:
            # Prüfe ob es eine Audio-Datei ist
            if file.suffix.lower() in ['.flac', '.wav', '.mp3']:
                try:
                    file.unlink()
                    deleted_files.append(file.name)
                except Exception as e:
                    errors.append(f"Fehler beim Löschen von {file.name}: {e}")
    
    # Finde und lösche Cover-Art
    # Versuche verschiedene Cover-Namen
    cover_patterns = [
        f"{base_name}_cover.jpg",
        f"{base_name}_cover.png"
    ]
    
    # Prüfe auch nach Cover-Dateien die zu Tracks gehören
    if track_files:
        # Verwende den ersten Track um Album-Info zu bekommen
        try:
            from mutagen.flac import FLAC
            audio = FLAC(str(track_files[0]))
            album = audio.get('ALBUM', [''])[0]
            artist = audio.get('ALBUMARTIST', audio.get('ARTIST', [''])[0])[0]
            if album and artist:
                # Suche nach Cover mit Album-Key Format
                album_key = f"{artist} - {album}"
                safe_key = "".join(c for c in album_key if c.isalnum() or c in (' ', '-', '_')).strip().replace(' ', '_')
                cover_patterns.append(f"{safe_key}_cover.jpg")
        except:
            pass
    
    for pattern in cover_patterns:
        cover_file = RECORDINGS_DIR / pattern
        if cover_file.exists() and cover_file.name not in deleted_files:
            try:
                cover_file.unlink()
                deleted_files.append(cover_file.name)
            except Exception as e:
                errors.append(f"Fehler beim Löschen von {cover_file.name}: {e}")
    
    # Suche auch nach allen Cover-Dateien die zu diesem Album gehören könnten
    for file in RECORDINGS_DIR.glob("*_cover.jpg"):
        if file.name in deleted_files:
            continue
        try:
            # Prüfe ob Cover zu einem Track dieses Albums gehört
            cover_base = file.stem.replace('_cover', '')
            matching_tracks = list(RECORDINGS_DIR.glob(f"{cover_base}_track_*.flac"))
            if matching_tracks:
                # Prüfe ob einer der Tracks zu unserem Album gehört
                for track_file in matching_tracks:
                    track_base = track_file.stem.split('_track_')[0]
                    if track_base == base_name:
                        file.unlink()
                        deleted_files.append(file.name)
                        break
        except Exception as e:
            pass  # Ignoriere Fehler bei Cover-Prüfung
    
    if not deleted_files:
        return JSONResponse(
            {"error": "Keine Dateien für Album gefunden"}, 
            status_code=404
        )
    
    return {
        "status": "deleted",
        "deleted_files": deleted_files,
        "count": len(deleted_files),
        "errors": errors if errors else None
    }

@app.get("/api/settings")
async def get_settings():
    """Hole alle Einstellungen"""
    return {
        "audio": config.get("audio", {}),
        "naming": config.get("naming", {}),
        "recording": config.get("recording", {})
    }

from typing import Optional

@app.post("/api/settings")
async def update_settings(
    audio_device_index: Optional[int] = Form(None),
    audio_device_name: Optional[str] = Form(None),
    audio_alsa_device: Optional[str] = Form(None),
    audio_sample_rate: Optional[int] = Form(None),
    audio_channels: Optional[int] = Form(None),
    naming_pattern: Optional[str] = Form(None),
    naming_use_timestamp: Optional[bool] = Form(None),
    recording_silence_threshold: Optional[float] = Form(None),
    recording_min_silence_duration: Optional[float] = Form(None),
    recording_min_track_duration: Optional[float] = Form(None),
    recording_auto_stop_silence_duration: Optional[float] = Form(None)
):
    """Aktualisiere Einstellungen"""
    try:
        # Audio-Einstellungen
        if audio_device_index is not None:
            config.set("audio.device_index", audio_device_index if audio_device_index >= 0 else None)
        if audio_device_name is not None:
            config.set("audio.device_name", audio_device_name)
        if audio_alsa_device is not None:
            config.set("audio.alsa_device", audio_alsa_device)
        if audio_sample_rate is not None:
            config.set("audio.sample_rate", audio_sample_rate)
        if audio_channels is not None:
            config.set("audio.channels", audio_channels)
        
        # Naming-Einstellungen
        if naming_pattern is not None:
            config.set("naming.pattern", naming_pattern)
        if naming_use_timestamp is not None:
            config.set("naming.use_timestamp", naming_use_timestamp)
        
        # Recording-Einstellungen
        if recording_silence_threshold is not None:
            config.set("recording.silence_threshold_db", recording_silence_threshold)
        if recording_min_silence_duration is not None:
            config.set("recording.min_silence_duration", recording_min_silence_duration)
        if recording_min_track_duration is not None:
            config.set("recording.min_track_duration", recording_min_track_duration)
        if recording_auto_stop_silence_duration is not None:
            config.set("recording.auto_stop_silence_duration", recording_auto_stop_silence_duration)
        
        # AudioRecorder neu initialisieren wenn Gerät geändert wurde
        if recorder is not None and not recorder.is_recording():
            try:
                sample_rate = config.get("audio.sample_rate", 44100)
                channels = config.get("audio.channels", 2)
                
                if isinstance(recorder, ALSARecorder):
                    # ALSA-Recorder
                    if audio_alsa_device is not None:
                        recorder.set_device(audio_alsa_device)
                    recorder.sample_rate = sample_rate
                    recorder.channels = channels
                else:
                    # PyAudio-Recorder
                    if audio_device_index is not None:
                        device_index = audio_device_index if audio_device_index >= 0 else None
                        recorder.set_device(device_index)
                    recorder.sample_rate = sample_rate
                    recorder.channels = channels
                    recorder.chunk = config.get("audio.chunk_size", 4096)
            except Exception as e:
                return JSONResponse(
                    {"error": f"Fehler beim Ändern des Geräts: {e}"},
                    status_code=500
                )
        
        # AudioRecorder / TrackSplitter Einstellungen aktualisieren
        silence_threshold_db = config.get("recording.silence_threshold_db", -40)
        min_silence = config.get("recording.min_silence_duration", 2.0)
        min_track = config.get("recording.min_track_duration", 10.0)
        auto_stop = config.get("recording.auto_stop_silence_duration", 10.0)

        splitter.silence_threshold = silence_threshold_db
        splitter.min_silence_duration = min_silence
        splitter.min_track_duration = min_track

        if recorder is not None and not recorder.is_recording():
            if hasattr(recorder, "silence_threshold_db"):
                recorder.silence_threshold_db = silence_threshold_db
            if hasattr(recorder, "auto_stop_silence_seconds"):
                recorder.auto_stop_silence_seconds = auto_stop
            # Für ALSA-Recorder auch silence_threshold_db setzen
            if isinstance(recorder, ALSARecorder):
                recorder.silence_threshold_db = silence_threshold_db
                recorder.auto_stop_silence_seconds = auto_stop
        
        return {"status": "success", "settings": config.config}
    except Exception as e:
        return JSONResponse(
            {"error": str(e)},
            status_code=500
        )

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            if recorder and recorder.is_recording():
                level = recorder.get_current_level()
                await websocket.send_json({
                    "type": "level",
                    "value": level
                })
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8045)


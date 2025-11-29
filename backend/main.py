from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import uvicorn
import os
import json
from pathlib import Path
from datetime import datetime
from audio_recorder import AudioRecorder
from track_splitter import TrackSplitter
from tagger import AudioTagger
from config import Config
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

# Frontend statisch servieren
try:
    if FRONTEND_DIR.exists():
        # Serviere statische Dateien (app.js, styles.css) direkt
        app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
    else:
        print(f"Warnung: Frontend-Verzeichnis nicht gefunden: {FRONTEND_DIR}")
except Exception as e:
    print(f"Warnung: Frontend-Verzeichnis nicht gefunden: {e}")

# Explizite Routen für statische Dateien
@app.get("/app.js")
async def serve_app_js():
    js_path = FRONTEND_DIR / "app.js"
    if js_path.exists():
        return FileResponse(str(js_path), media_type="application/javascript")
    raise FileNotFoundError("app.js nicht gefunden")

@app.get("/styles.css")
async def serve_styles_css():
    css_path = FRONTEND_DIR / "styles.css"
    if css_path.exists():
        return FileResponse(str(css_path), media_type="text/css")
    raise FileNotFoundError("styles.css nicht gefunden")

@app.get("/favicon.ico")
async def serve_favicon():
    # Einfach 204 No Content zurückgeben, da kein Favicon vorhanden
    from fastapi.responses import Response
    return Response(status_code=204)

# Globale Instanzen - mit Fehlerbehandlung
try:
    device_index = config.get("audio.device_index")
    sample_rate = config.get("audio.sample_rate", 44100)
    channels = config.get("audio.channels", 2)
    chunk_size = config.get("audio.chunk_size", 4096)
    recorder = AudioRecorder(
        device_index=device_index,
        sample_rate=sample_rate,
        channels=channels,
        chunk=chunk_size
    )
except Exception as e:
    print(f"Warnung: AudioRecorder konnte nicht initialisiert werden: {e}")
    recorder = None

# TrackSplitter mit Konfiguration initialisieren
splitter = TrackSplitter()
splitter.silence_threshold = config.get("recording.silence_threshold_db", -40)
splitter.min_silence_duration = config.get("recording.min_silence_duration", 2.0)
splitter.min_track_duration = config.get("recording.min_track_duration", 10.0)

tagger = AudioTagger()

@app.get("/")
async def read_root():
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise FileNotFoundError(f"Frontend-Datei nicht gefunden: {index_path}")
    return FileResponse(str(index_path))

@app.get("/api/status")
async def get_status():
    if recorder is None:
        return {
            "recording": False,
            "devices": [],
            "alsa_devices": [],
            "error": "AudioRecorder nicht verfügbar"
        }
    
    # PyAudio-Geräte
    pyaudio_devices = recorder.get_audio_devices()
    
    # ALSA-Geräte
    alsa_devices = Config.get_alsa_devices()
    
    return {
        "recording": recorder.is_recording(),
        "devices": pyaudio_devices,
        "alsa_devices": alsa_devices,
        "current_device_index": recorder.device_index
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
    return {"filename": filename, "status": "recording_stopped"}

@app.get("/api/recordings")
async def list_recordings():
    recordings = []
    for file in RECORDINGS_DIR.glob("*.flac"):
        recordings.append({
            "filename": file.name,
            "size": file.stat().st_size,
            "created": file.stat().st_mtime
        })
    return {"recordings": sorted(recordings, key=lambda x: x["created"], reverse=True)}

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

@app.delete("/api/delete/{filename}")
async def delete_recording(filename: str):
    filepath = RECORDINGS_DIR / filename
    if filepath.exists():
        filepath.unlink()
        return {"status": "deleted"}
    return JSONResponse(
        {"error": "Datei nicht gefunden"}, 
        status_code=404
    )

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
    audio_sample_rate: Optional[int] = Form(None),
    audio_channels: Optional[int] = Form(None),
    naming_pattern: Optional[str] = Form(None),
    naming_use_timestamp: Optional[bool] = Form(None),
    recording_silence_threshold: Optional[float] = Form(None),
    recording_min_silence_duration: Optional[float] = Form(None),
    recording_min_track_duration: Optional[float] = Form(None)
):
    """Aktualisiere Einstellungen"""
    try:
        # Audio-Einstellungen
        if audio_device_index is not None:
            config.set("audio.device_index", audio_device_index if audio_device_index >= 0 else None)
        if audio_device_name is not None:
            config.set("audio.device_name", audio_device_name)
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
        
        # AudioRecorder neu initialisieren wenn Gerät geändert wurde
        if audio_device_index is not None and recorder is not None:
            if not recorder.is_recording():
                try:
                    device_index = audio_device_index if audio_device_index >= 0 else None
                    sample_rate = config.get("audio.sample_rate", 44100)
                    channels = config.get("audio.channels", 2)
                    chunk_size = config.get("audio.chunk_size", 4096)
                    recorder.set_device(device_index)
                    recorder.sample_rate = sample_rate
                    recorder.channels = channels
                    recorder.chunk = chunk_size
                except Exception as e:
                    return JSONResponse(
                        {"error": f"Fehler beim Ändern des Geräts: {e}"},
                        status_code=500
                    )
        
        # TrackSplitter-Einstellungen aktualisieren
        splitter.silence_threshold = config.get("recording.silence_threshold_db", -40)
        splitter.min_silence_duration = config.get("recording.min_silence_duration", 2.0)
        splitter.min_track_duration = config.get("recording.min_track_duration", 10.0)
        
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


from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import json
from pathlib import Path
from audio_recorder import AudioRecorder
from track_splitter import TrackSplitter
from tagger import AudioTagger
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

# Verzeichnisse erstellen
RECORDINGS_DIR.mkdir(exist_ok=True)

# Frontend statisch servieren
try:
    if FRONTEND_DIR.exists():
        app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")
    else:
        print(f"Warnung: Frontend-Verzeichnis nicht gefunden: {FRONTEND_DIR}")
except Exception as e:
    print(f"Warnung: Frontend-Verzeichnis nicht gefunden: {e}")

# Globale Instanzen - mit Fehlerbehandlung
try:
    recorder = AudioRecorder()
except Exception as e:
    print(f"Warnung: AudioRecorder konnte nicht initialisiert werden: {e}")
    recorder = None

splitter = TrackSplitter()
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
            "error": "AudioRecorder nicht verfügbar"
        }
    return {
        "recording": recorder.is_recording(),
        "devices": recorder.get_audio_devices()
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
    
    filename = recorder.start_recording(RECORDINGS_DIR)
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


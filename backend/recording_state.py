import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

class RecordingState:
    """Verwaltet den persistenten Aufnahme-Status"""
    
    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.state = {
            "is_recording": False,
            "filename": None,
            "start_time": None,
            "recorder_type": None,  # "pyaudio" oder "alsa"
            "device": None
        }
        self.load()
    
    def load(self) -> Dict[str, Any]:
        """Lade Status aus Datei"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    self.state = json.load(f)
            except Exception as e:
                print(f"Fehler beim Laden des Aufnahme-Status: {e}")
                self.state = {
                    "is_recording": False,
                    "filename": None,
                    "start_time": None,
                    "recorder_type": None,
                    "device": None
                }
        return self.state
    
    def save(self):
        """Speichere Status in Datei"""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Fehler beim Speichern des Aufnahme-Status: {e}")
    
    def start_recording(self, filename: str, recorder_type: str, device: Any = None):
        """Markiere Aufnahme als gestartet"""
        self.state = {
            "is_recording": True,
            "filename": filename,
            "start_time": datetime.now().isoformat(),
            "recorder_type": recorder_type,
            "device": str(device) if device is not None else None
        }
        self.save()
    
    def stop_recording(self):
        """Markiere Aufnahme als gestoppt"""
        self.state = {
            "is_recording": False,
            "filename": None,
            "start_time": None,
            "recorder_type": None,
            "device": None
        }
        self.save()
    
    def is_recording(self) -> bool:
        """Prüfe ob Aufnahme läuft"""
        return self.state.get("is_recording", False)
    
    def get_filename(self) -> Optional[str]:
        """Hole Dateiname der aktuellen Aufnahme"""
        return self.state.get("filename")



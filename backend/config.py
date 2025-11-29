import json
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

class Config:
    def __init__(self, config_file: Path):
        self.config_file = config_file
        self.default_config = {
            "audio": {
                "device_index": None,  # None = Standard-Gerät
                "device_name": None,
                "alsa_device": "hw:1,0",  # ALSA-Gerät (z.B. hw:1,0)
                "sample_rate": 44100,
                "channels": 2,
                "chunk_size": 4096
            },
            "naming": {
                "pattern": "{artist} - {album} - {date}",  # Pattern für Dateinamen
                "use_timestamp": True,
                "timestamp_format": "%Y%m%d_%H%M%S"
            },
            "recording": {
                "auto_split": True,
                "silence_threshold_db": -40,
                "min_silence_duration": 2.0,
                "min_track_duration": 10.0
            }
        }
        self.config = self.load()
    
    def load(self) -> Dict[str, Any]:
        """Lade Konfiguration aus Datei"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    # Merge mit Defaults für neue Optionen
                    config = self.default_config.copy()
                    for key, value in loaded.items():
                        if isinstance(value, dict) and key in config:
                            config[key].update(value)
                        else:
                            config[key] = value
                    return config
            except Exception as e:
                print(f"Fehler beim Laden der Konfiguration: {e}")
                return self.default_config.copy()
        return self.default_config.copy()
    
    def save(self):
        """Speichere Konfiguration in Datei"""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Fehler beim Speichern der Konfiguration: {e}")
    
    def get(self, key_path: str, default=None):
        """Hole Wert aus verschachtelter Konfiguration"""
        keys = key_path.split('.')
        value = self.config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value
    
    def set(self, key_path: str, value: Any):
        """Setze Wert in verschachtelter Konfiguration"""
        keys = key_path.split('.')
        config = self.config
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]
        config[keys[-1]] = value
        self.save()
    
    @staticmethod
    def get_alsa_devices():
        """Liste ALSA-Geräte auf"""
        devices = []
        try:
            # Verwende arecord -l um ALSA-Geräte zu listen
            result = subprocess.run(
                ['arecord', '-l'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if 'card' in line.lower():
                        # Parse Zeile wie: "card 1: Device [USB Audio Device], device 0: USB Audio [USB Audio]"
                        parts = line.split(':')
                        if len(parts) >= 2:
                            card_part = parts[0].strip()
                            device_name = parts[1].split(',')[0].strip()
                            
                            # Extrahiere Card-Nummer
                            try:
                                card_num = int(card_part.split()[1])
                                devices.append({
                                    "name": device_name,
                                    "alsa_id": f"hw:{card_num},0",
                                    "card": card_num,
                                    "device": 0
                                })
                            except (ValueError, IndexError):
                                pass
        except FileNotFoundError:
            print("arecord nicht gefunden - ALSA-Geräte können nicht aufgelistet werden")
        except Exception as e:
            print(f"Fehler beim Auflisten der ALSA-Geräte: {e}")
        
        return devices


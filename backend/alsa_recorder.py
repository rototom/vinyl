import subprocess
import soundfile as sf
import numpy as np
from datetime import datetime
from pathlib import Path
import threading
import time
import os

class ALSARecorder:
    """Audio-Recorder der ALSA direkt verwendet (arecord)"""
    
    def __init__(self, alsa_device="hw:1,0", sample_rate=44100, channels=2):
        self.alsa_device = alsa_device
        self.sample_rate = sample_rate
        self.channels = channels
        self._is_recording = False
        self.process = None
        self.filename = None
        self.output_path = None
        self.current_level = 0.0
        self._level_thread = None
        
    def get_alsa_devices(self):
        """Liste verfügbarer ALSA-Geräte"""
        devices = []
        try:
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
                        try:
                            card_part = line.split(':')[0].strip()
                            card_num = int(card_part.split()[1])
                            device_name = line.split(':')[1].split(',')[0].strip()
                            devices.append({
                                "name": device_name,
                                "alsa_id": f"hw:{card_num},0",
                                "card": card_num,
                                "device": 0
                            })
                        except (ValueError, IndexError):
                            pass
        except FileNotFoundError:
            print("arecord nicht gefunden")
        except Exception as e:
            print(f"Fehler beim Auflisten der ALSA-Geräte: {e}")
        
        return devices
    
    def _monitor_level(self, temp_file):
        """Überwache Audio-Level während der Aufnahme"""
        while self._is_recording:
            try:
                if temp_file.exists() and temp_file.stat().st_size > 0:
                    # Lese letzten Teil der Datei für Level-Berechnung
                    data, sr = sf.read(str(temp_file), start=-self.sample_rate, always_2d=True)
                    if len(data) > 0:
                        # Berechne RMS-Level
                        rms = np.sqrt(np.mean(data**2))
                        self.current_level = float(rms)
                time.sleep(0.1)
            except Exception:
                time.sleep(0.1)
    
    def start_recording(self, output_dir: Path, filename_template: str = None):
        """Starte Aufnahme mit arecord"""
        if self._is_recording:
            return None
        
        # Prüfe ob Gerät verfügbar ist
        devices = self.get_alsa_devices()
        device_found = False
        for dev in devices:
            if dev['alsa_id'] == self.alsa_device:
                device_found = True
                break
        
        if not device_found and devices:
            # Verwende erstes verfügbares Gerät
            self.alsa_device = devices[0]['alsa_id']
            print(f"Verwende ALSA-Gerät: {self.alsa_device}")
        
        self._is_recording = True
        
        # Generiere Dateinamen
        if filename_template:
            self.filename = filename_template
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.filename = f"recording_{timestamp}.wav"
        
        self.output_path = output_dir / self.filename
        temp_wav = self.output_path
        
        try:
            # Starte arecord-Prozess
            cmd = [
                'arecord',
                '-D', self.alsa_device,
                '-f', 'S16_LE',  # 16-bit signed little-endian
                '-r', str(self.sample_rate),
                '-c', str(self.channels),
                '-t', 'wav',
                str(temp_wav)
            ]
            
            print(f"Starte Aufnahme: {' '.join(cmd)}")
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Starte Level-Monitoring
            self._level_thread = threading.Thread(target=self._monitor_level, args=(temp_wav,), daemon=True)
            self._level_thread.start()
            
            return self.filename
            
        except Exception as e:
            self._is_recording = False
            raise Exception(f"Fehler beim Starten der ALSA-Aufnahme: {e}")
    
    def stop_recording(self):
        """Stoppe Aufnahme und konvertiere zu FLAC"""
        if not self._is_recording:
            return None
        
        self._is_recording = False
        
        # Stoppe arecord-Prozess
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        
        # Warte kurz, damit Datei geschrieben wird
        time.sleep(0.5)
        
        if not self.output_path.exists():
            raise Exception("Aufnahmedatei wurde nicht erstellt")
        
        # Konvertiere zu FLAC
        flac_filename = self.output_path.stem + ".flac"
        flac_path = self.output_path.parent / flac_filename
        
        try:
            # Lese WAV und schreibe als FLAC
            data, sr = sf.read(str(self.output_path))
            sf.write(str(flac_path), data, sr, format='FLAC')
            
            # Lösche temporäres WAV
            self.output_path.unlink()
            
            return flac_filename
            
        except Exception as e:
            raise Exception(f"Fehler beim Konvertieren zu FLAC: {e}")
    
    def is_recording(self):
        """Prüfe ob Aufnahme läuft"""
        return self._is_recording
    
    def get_current_level(self):
        """Aktuelles Audio-Level für Visualisierung"""
        return float(self.current_level)
    
    def set_device(self, alsa_device):
        """Setze ALSA-Gerät"""
        if self._is_recording:
            raise Exception("Gerät kann nicht während der Aufnahme geändert werden")
        self.alsa_device = alsa_device


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
        self.auto_stop_silence_seconds = 0.0  # 0.0 = deaktiviert
        self.silence_threshold_db = -40.0
        self._silence_duration = 0.0
        self._silence_start_time = None
        self._silence_stop_triggered = False
        
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
    
    def _kill_existing_arecord_processes(self):
        """Beende laufende arecord-Prozesse die das Gerät blockieren"""
        try:
            # Finde alle arecord-Prozesse
            result = subprocess.run(
                ['pgrep', '-f', 'arecord'],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode == 0:
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    if pid.strip():
                        try:
                            pid_int = int(pid.strip())
                            print(f"Beende arecord-Prozess PID {pid_int}...")
                            subprocess.run(['kill', '-TERM', str(pid_int)], timeout=1)
                            time.sleep(0.2)
                        except (ValueError, subprocess.TimeoutExpired):
                            pass
                if pids:
                    time.sleep(0.5)  # Warte kurz bis Prozesse beendet sind
        except FileNotFoundError:
            # pgrep nicht verfügbar, versuche mit ps
            try:
                result = subprocess.run(
                    ['ps', 'aux'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if 'arecord' in line and 'grep' not in line:
                            parts = line.split()
                            if len(parts) > 1:
                                try:
                                    pid = int(parts[1])
                                    print(f"Beende arecord-Prozess PID {pid}...")
                                    subprocess.run(['kill', '-TERM', str(pid)], timeout=1)
                                except (ValueError, IndexError):
                                    pass
                    time.sleep(0.5)
            except:
                pass
        except Exception as e:
            print(f"Warnung: Konnte laufende arecord-Prozesse nicht prüfen: {e}")
    
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
                        
                        # Prüfe Auto-Stop bei Stille
                        if self.auto_stop_silence_seconds > 0:
                            # Verwende eine niedrigere Schwelle für Auto-Stop als für Track-Splitting
                            # -50 dB ist sehr leise und deutet auf echte Stille hin
                            auto_stop_threshold_db = -50.0  # Niedrigere Schwelle für Auto-Stop
                            amplitude_threshold = 10 ** (auto_stop_threshold_db / 20.0)
                            
                            if self.current_level <= amplitude_threshold:
                                if self._silence_start_time is None:
                                    self._silence_start_time = time.time()
                                else:
                                    silence_duration = time.time() - self._silence_start_time
                                    if not self._silence_stop_triggered and silence_duration >= self.auto_stop_silence_seconds:
                                        self._silence_stop_triggered = True
                                        print(f"⚠️  Auto-Stop: Stille erkannt (Level: {self.current_level:.6f}, Schwelle: {amplitude_threshold:.6f}, Dauer: {silence_duration:.1f}s)")
                                        threading.Thread(target=self._stop_due_to_silence, daemon=True).start()
                            else:
                                # Reset nur wenn Level deutlich über Schwelle ist
                                if self.current_level > amplitude_threshold * 2:  # Mindestens doppelt so laut wie Schwelle
                                    self._silence_start_time = None
                                    self._silence_stop_triggered = False
                time.sleep(0.1)
            except Exception:
                time.sleep(0.1)
    
    def _stop_due_to_silence(self):
        """Stoppe Aufnahme aufgrund von Stille"""
        try:
            print(f"📢 Automatisches Stoppen nach {self.auto_stop_silence_seconds}s Stille (Level unter -50 dB)")
            self.stop_recording()
        except Exception as e:
            print(f"Fehler beim Stoppen aufgrund von Stille: {e}")
    
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
        
        # Prüfe ob bereits eine Aufnahme läuft
        if self._is_recording and self.process:
            raise Exception("Aufnahme läuft bereits")
        
        # Beende eventuell laufende arecord-Prozesse die das Gerät blockieren
        self._kill_existing_arecord_processes()
        
        self._is_recording = True
        self._silence_duration = 0.0
        self._silence_start_time = None
        self._silence_stop_triggered = False
        
        # Generiere Dateinamen
        if filename_template:
            self.filename = filename_template
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.filename = f"recording_{timestamp}.wav"
        
        self.output_path = output_dir / self.filename
        temp_wav = self.output_path
        
        # Stelle sicher, dass das Verzeichnis existiert
        output_dir.mkdir(parents=True, exist_ok=True)
        
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
            print(f"Ziel-Datei: {temp_wav}")
            
            # Öffne stderr für Fehlerausgabe
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0  # Unbuffered
            )
            
            # Prüfe kurz ob Prozess gestartet wurde
            time.sleep(0.2)
            if self.process.poll() is not None:
                # Prozess ist bereits beendet - Fehler!
                stderr_output = self.process.stderr.read().decode('utf-8', errors='ignore')
                error_msg = f"arecord-Prozess startete nicht. Fehler: {stderr_output}"
                
                # Prüfe ob "Device or resource busy" Fehler
                if "Device or resource busy" in stderr_output or "busy" in stderr_output.lower():
                    error_msg += "\n\nDas Gerät wird möglicherweise von einem anderen Prozess verwendet."
                    error_msg += "\nVersuche:"
                    error_msg += "\n1. Prüfe mit 'lsof /dev/snd/*' welche Prozesse das Gerät verwenden"
                    error_msg += f"\n2. Prüfe mit 'fuser -v /dev/snd/*' welche Prozesse das Gerät blockieren"
                    error_msg += f"\n3. Starte den Server neu"
                
                raise Exception(error_msg)
            
            print(f"arecord-Prozess läuft (PID: {self.process.pid})")
            
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
        self._silence_start_time = None
        self._silence_stop_triggered = False
        
        # Stoppe arecord-Prozess
        if self.process:
            # Sende SIGTERM um arecord sauber zu beenden
            self.process.terminate()
            try:
                # Warte bis zu 3 Sekunden auf Beendigung
                self.process.wait(timeout=3)
                print(f"arecord-Prozess beendet (Returncode: {self.process.returncode})")
            except subprocess.TimeoutExpired:
                print("arecord-Prozess reagiert nicht, erzwinge Beendigung...")
                self.process.kill()
                self.process.wait()
            
            # Prüfe stderr für Fehler
            if self.process.stderr:
                stderr_output = self.process.stderr.read().decode('utf-8', errors='ignore')
                if stderr_output:
                    print(f"arecord stderr: {stderr_output}")
        
        # Warte länger, damit Datei vollständig geschrieben wird
        max_wait = 5
        waited = 0
        while waited < max_wait:
            if self.output_path.exists() and self.output_path.stat().st_size > 0:
                print(f"Aufnahmedatei gefunden: {self.output_path} ({self.output_path.stat().st_size} Bytes)")
                break
            time.sleep(0.5)
            waited += 0.5
        
        if not self.output_path.exists():
            # Prüfe ob Datei an anderem Ort erstellt wurde
            possible_paths = [
                self.output_path.parent / self.filename,
                Path(self.filename),
                Path.cwd() / self.filename
            ]
            
            found = False
            for path in possible_paths:
                if path.exists():
                    print(f"Aufnahmedatei an unerwartetem Ort gefunden: {path}")
                    self.output_path = path
                    found = True
                    break
            
            if not found:
                raise Exception(
                    f"Aufnahmedatei wurde nicht erstellt. Erwarteter Pfad: {self.output_path}\n"
                    f"arecord Returncode: {self.process.returncode if self.process else 'N/A'}"
                )
        
        # Prüfe ob Datei groß genug ist (mindestens Header-Größe)
        file_size = self.output_path.stat().st_size
        if file_size < 44:  # WAV-Header ist mindestens 44 Bytes
            raise Exception(f"Aufnahmedatei ist zu klein ({file_size} Bytes) - möglicherweise leer")
        
        # Konvertiere zu FLAC
        flac_filename = self.output_path.stem + ".flac"
        flac_path = self.output_path.parent / flac_filename
        
        try:
            # Lese WAV und schreibe als FLAC
            print(f"Konvertiere {self.output_path} zu FLAC...")
            data, sr = sf.read(str(self.output_path))
            print(f"Audio-Daten geladen: {len(data)} Samples, {sr} Hz, {data.shape}")
            sf.write(str(flac_path), data, sr, format='FLAC')
            print(f"FLAC-Datei erstellt: {flac_path}")
            
            # Lösche temporäres WAV
            self.output_path.unlink()
            
            return flac_filename
            
        except Exception as e:
            import traceback
            traceback.print_exc()
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


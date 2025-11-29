import pyaudio
import wave
import soundfile as sf
import numpy as np
from datetime import datetime
from pathlib import Path
import threading
import time
import subprocess

class AudioRecorder:
    def __init__(self, device_index=None, sample_rate=44100, channels=2, chunk=4096):
        try:
            self.audio = pyaudio.PyAudio()
            self._audio_available = True
            
            # Zeige verfügbare Host-APIs (Backends)
            print("Verfügbare PyAudio Host-APIs:")
            for i in range(self.audio.get_host_api_count()):
                try:
                    api_info = self.audio.get_host_api_info_by_index(i)
                    print(f"  {i}: {api_info.get('name', 'Unbekannt')} (Typ: {api_info.get('type', 'Unbekannt')})")
                except:
                    pass
        except Exception as e:
            print(f"Warnung: PyAudio konnte nicht initialisiert werden: {e}")
            self.audio = None
            self._audio_available = False
        
        self.device_index = device_index
        self._is_recording = False
        self.frames = []
        self.stream = None
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk = chunk
        self.format = pyaudio.paInt16 if self._audio_available else None
        self.current_level = 0.0
        self.filename = None
        self.output_path = None
        self.silence_threshold_db = -40.0
        self.auto_stop_silence_seconds = 10.0
        self._silence_duration = 0.0
        self._silence_stop_triggered = False
    
    def set_device(self, device_index):
        """Setze Audio-Gerät"""
        if self._is_recording:
            raise Exception("Gerät kann nicht während der Aufnahme geändert werden")
        self.device_index = device_index
        
    def get_alsa_device_mapping(self):
        """Erstelle Mapping zwischen ALSA-Geräten und PyAudio-Geräten"""
        mapping = {}
        try:
            # Hole ALSA-Geräte
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
                            mapping[card_num] = device_name
                        except:
                            pass
        except:
            pass
        
        return mapping
    
    def get_audio_devices(self):
        """Liste verfügbarer Audio-Geräte"""
        if not self._audio_available or self.audio is None:
            return []
        devices = []
        try:
            device_count = self.audio.get_device_count()
            print(f"PyAudio: {device_count} Geräte gefunden")
            
            if device_count == 0:
                print("Warnung: PyAudio findet keine Geräte")
                return []
            
            # Hole ALSA-Mapping für Vergleich
            alsa_mapping = self.get_alsa_device_mapping()
            
            for i in range(device_count):
                try:
                    info = self.audio.get_device_info_by_index(i)
                    max_input = info.get('maxInputChannels', 0)
                    max_output = info.get('maxOutputChannels', 0)
                    device_name = info.get('name', 'Unbekannt')
                    host_api = info.get('hostApi', -1)
                    
                    # Hole Host-API-Info
                    host_api_name = "Unbekannt"
                    try:
                        if host_api >= 0:
                            api_info = self.audio.get_host_api_info_by_index(host_api)
                            host_api_name = api_info.get('name', 'Unbekannt')
                    except:
                        pass
                    
                    print(f"Gerät {i}: {device_name} - Input: {max_input}, Output: {max_output}, Backend: {host_api_name}")
                    
                    # Versuche ALSA-Gerät zuzuordnen
                    alsa_match = None
                    for card_num, alsa_name in alsa_mapping.items():
                        if alsa_name.lower() in device_name.lower() or device_name.lower() in alsa_name.lower():
                            alsa_match = f"hw:{card_num},0"
                            break
                    
                    if max_input > 0:
                        device_info = {
                            "index": i,
                            "name": device_name,
                            "channels": max_input,
                            "sample_rate": info.get('defaultSampleRate', 44100),
                            "host_api": host_api,
                            "host_api_name": host_api_name
                        }
                        if alsa_match:
                            device_info["alsa_id"] = alsa_match
                        devices.append(device_info)
                except Exception as e:
                    print(f"Fehler beim Abrufen von Gerät {i}: {e}")
                    continue
            
            print(f"Gefundene Input-Geräte: {len(devices)}")
            if devices:
                for dev in devices:
                    alsa_info = f" (ALSA: {dev.get('alsa_id', 'N/A')})" if dev.get('alsa_id') else ""
                    print(f"  - Index {dev['index']}: {dev['name']} ({dev['channels']} Kanäle, {dev['host_api_name']}){alsa_info}")
            else:
                print("⚠️  Keine Input-Geräte gefunden!")
                print("   Versuche Standard-Input-Gerät...")
                try:
                    default_info = self.audio.get_default_input_device_info()
                    if default_info:
                        print(f"   Standard-Input: {default_info.get('name')} (Index: {default_info.get('index')})")
                except Exception as e:
                    print(f"   Standard-Input nicht verfügbar: {e}")
            
        except Exception as e:
            print(f"Fehler beim Abrufen der Audio-Geräte: {e}")
            import traceback
            traceback.print_exc()
        
        return devices
    
    def find_available_input_device(self):
        """Finde ein verfügbares Input-Gerät"""
        devices = self.get_audio_devices()
        if not devices:
            # Versuche Standard-Input-Gerät zu verwenden
            try:
                default_info = self.audio.get_default_input_device_info()
                if default_info and default_info.get('maxInputChannels', 0) > 0:
                    print(f"Verwende Standard-Input-Gerät: {default_info.get('name')}")
                    return default_info.get('index')
            except Exception as e:
                print(f"Standard-Input-Gerät nicht verfügbar: {e}")
            return None
        
        # Wenn ein Gerät konfiguriert ist, prüfe ob es noch verfügbar ist
        if self.device_index is not None:
            for device in devices:
                if device['index'] == self.device_index:
                    print(f"Verwende konfiguriertes Gerät: {device['name']} (Index {device['index']})")
                    return self.device_index
        
        # Verwende das erste verfügbare Gerät
        if devices:
            print(f"Verwende erstes verfügbares Gerät: {devices[0]['name']} (Index {devices[0]['index']})")
            return devices[0]['index']
        
        return None
    
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """Callback für Audio-Stream"""
        if self._is_recording:
            self.frames.append(in_data)
            # Berechne Audio-Level für Visualisierung
            audio_data = np.frombuffer(in_data, dtype=np.int16)
            self.current_level = np.abs(audio_data).mean() / 32768.0
            self._check_auto_stop(self.current_level, frame_count / self.sample_rate)
        return (in_data, pyaudio.paContinue)

    def _check_auto_stop(self, level, chunk_duration):
        if not self.auto_stop_silence_seconds or self.auto_stop_silence_seconds <= 0:
            return
        amplitude_threshold = 10 ** (self.silence_threshold_db / 20.0) if self.silence_threshold_db is not None else 0.01
        if level <= amplitude_threshold:
            self._silence_duration += chunk_duration
            if not self._silence_stop_triggered and self._silence_duration >= self.auto_stop_silence_seconds:
                self._silence_stop_triggered = True
                threading.Thread(target=self._stop_due_to_silence, daemon=True).start()
        else:
            self._silence_duration = 0.0
            self._silence_stop_triggered = False

    def _stop_due_to_silence(self):
        try:
            print(f"📢 Automatisches Stoppen nach {self.auto_stop_silence_seconds}s Stille")
            self.stop_recording()
        except Exception as e:
            print(f"Fehler beim Stoppen aufgrund von Stille: {e}")
    
    def start_recording(self, output_dir: Path, filename_template: str = None):
        """Starte Aufnahme"""
        if not self._audio_available or self.audio is None:
            raise Exception("AudioRecorder nicht verfügbar - PyAudio konnte nicht initialisiert werden")
        
        if self._is_recording:
            return None
        
        # Finde ein verfügbares Input-Gerät
        available_devices = self.get_audio_devices()
        if not available_devices:
            raise Exception("Keine Audio-Input-Geräte gefunden. Bitte ein Gerät anschließen und in den Einstellungen auswählen.")
        
        # Bestimme das zu verwendende Gerät
        input_device_index = self.find_available_input_device()
        if input_device_index is None:
            input_device_index = available_devices[0]['index']
        
        # Prüfe Gerät-Info
        try:
            device_info = self.audio.get_device_info_by_index(input_device_index)
            if device_info['maxInputChannels'] == 0:
                raise Exception(f"Gerät {input_device_index} ({device_info['name']}) hat keine Input-Kanäle")
        except Exception as e:
            raise Exception(f"Gerät {input_device_index} ist nicht verfügbar: {e}")
        
        self.frames = []
        self._is_recording = True
        self._silence_duration = 0.0
        self._silence_stop_triggered = False
        
        try:
            # Versuche mit konfigurierten Einstellungen
            self.stream = self.audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=input_device_index,
                frames_per_buffer=self.chunk,
                stream_callback=self._audio_callback
            )
            
            self.stream.start_stream()
        except OSError as e:
            self._is_recording = False
            error_msg = str(e)
            if "Invalid input device" in error_msg or "-9996" in error_msg:
                raise Exception(
                    f"Audio-Gerät {input_device_index} ist nicht verfügbar oder nicht kompatibel. "
                    f"Verfügbare Geräte: {[d['index'] for d in available_devices]}. "
                    f"Bitte ein anderes Gerät in den Einstellungen auswählen."
                )
            else:
                raise Exception(f"Fehler beim Starten der Aufnahme: {e}")
        except Exception as e:
            self._is_recording = False
            raise Exception(f"Fehler beim Starten der Aufnahme: {e}")
        
        # Verwende Template oder Standard-Benennung
        if filename_template:
            self.filename = filename_template
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.filename = f"recording_{timestamp}.wav"
        
        self.output_path = output_dir / self.filename
        
        return self.filename
    
    def stop_recording(self):
        """Stoppe Aufnahme und speichere als FLAC"""
        if not self._is_recording:
            return None
        
        self._is_recording = False
        
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        
        # Konvertiere zu FLAC
        flac_filename = self.output_path.stem + ".flac"
        flac_path = self.output_path.parent / flac_filename
        
        # Speichere als WAV zuerst
        wf = wave.open(str(self.output_path), 'wb')
        wf.setnchannels(self.channels)
        wf.setsampwidth(self.audio.get_sample_size(self.format))
        wf.setframerate(self.sample_rate)
        wf.writeframes(b''.join(self.frames))
        wf.close()
        
        # Konvertiere zu FLAC
        data, sr = sf.read(str(self.output_path))
        sf.write(str(flac_path), data, sr, format='FLAC')
        
        # Lösche temporäres WAV
        self.output_path.unlink()
        
        return flac_filename
    
    def is_recording(self):
        """Prüfe ob Aufnahme läuft"""
        return self._is_recording
    
    def get_current_level(self):
        """Aktuelles Audio-Level für Visualisierung"""
        return float(self.current_level)


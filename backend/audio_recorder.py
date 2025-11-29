import pyaudio
import wave
import soundfile as sf
import numpy as np
from datetime import datetime
from pathlib import Path
import threading
import time

class AudioRecorder:
    def __init__(self, device_index=None, sample_rate=44100, channels=2, chunk=4096):
        try:
            self.audio = pyaudio.PyAudio()
            self._audio_available = True
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
    
    def set_device(self, device_index):
        """Setze Audio-Gerät"""
        if self._is_recording:
            raise Exception("Gerät kann nicht während der Aufnahme geändert werden")
        self.device_index = device_index
        
    def get_audio_devices(self):
        """Liste verfügbarer Audio-Geräte"""
        if not self._audio_available or self.audio is None:
            return []
        devices = []
        try:
            for i in range(self.audio.get_device_count()):
                try:
                    info = self.audio.get_device_info_by_index(i)
                    if info['maxInputChannels'] > 0:
                        devices.append({
                            "index": i,
                            "name": info['name'],
                            "channels": info['maxInputChannels'],
                            "sample_rate": info.get('defaultSampleRate', 44100)
                        })
                except Exception as e:
                    print(f"Fehler beim Abrufen von Gerät {i}: {e}")
                    continue
        except Exception as e:
            print(f"Fehler beim Abrufen der Audio-Geräte: {e}")
        return devices
    
    def find_available_input_device(self):
        """Finde ein verfügbares Input-Gerät"""
        devices = self.get_audio_devices()
        if not devices:
            return None
        
        # Wenn ein Gerät konfiguriert ist, prüfe ob es noch verfügbar ist
        if self.device_index is not None:
            for device in devices:
                if device['index'] == self.device_index:
                    return self.device_index
        
        # Verwende das erste verfügbare Gerät
        return devices[0]['index']
    
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """Callback für Audio-Stream"""
        if self._is_recording:
            self.frames.append(in_data)
            # Berechne Audio-Level für Visualisierung
            audio_data = np.frombuffer(in_data, dtype=np.int16)
            self.current_level = np.abs(audio_data).mean() / 32768.0
        return (in_data, pyaudio.paContinue)
    
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


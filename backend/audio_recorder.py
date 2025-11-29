import pyaudio
import wave
import soundfile as sf
import numpy as np
from datetime import datetime
from pathlib import Path
import threading
import time

class AudioRecorder:
    def __init__(self):
        try:
            self.audio = pyaudio.PyAudio()
            self._audio_available = True
        except Exception as e:
            print(f"Warnung: PyAudio konnte nicht initialisiert werden: {e}")
            self.audio = None
            self._audio_available = False
        
        self._is_recording = False
        self.frames = []
        self.stream = None
        self.sample_rate = 44100
        self.channels = 2
        self.chunk = 4096
        self.format = pyaudio.paInt16 if self._audio_available else None
        self.current_level = 0.0
        self.filename = None
        self.output_path = None
        
    def get_audio_devices(self):
        """Liste verfügbarer Audio-Geräte"""
        if not self._audio_available or self.audio is None:
            return []
        devices = []
        try:
            for i in range(self.audio.get_device_count()):
                info = self.audio.get_device_info_by_index(i)
                if info['maxInputChannels'] > 0:
                    devices.append({
                        "index": i,
                        "name": info['name'],
                        "channels": info['maxInputChannels']
                    })
        except Exception as e:
            print(f"Fehler beim Abrufen der Audio-Geräte: {e}")
        return devices
    
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """Callback für Audio-Stream"""
        if self._is_recording:
            self.frames.append(in_data)
            # Berechne Audio-Level für Visualisierung
            audio_data = np.frombuffer(in_data, dtype=np.int16)
            self.current_level = np.abs(audio_data).mean() / 32768.0
        return (in_data, pyaudio.paContinue)
    
    def start_recording(self, output_dir: Path):
        """Starte Aufnahme"""
        if not self._audio_available or self.audio is None:
            raise Exception("AudioRecorder nicht verfügbar - PyAudio konnte nicht initialisiert werden")
        
        if self._is_recording:
            return None
        
        self.frames = []
        self._is_recording = True
        
        try:
            # Standard-Input-Gerät verwenden (kann konfiguriert werden)
            self.stream = self.audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk,
                stream_callback=self._audio_callback
            )
            
            self.stream.start_stream()
        except Exception as e:
            self._is_recording = False
            raise Exception(f"Fehler beim Starten der Aufnahme: {e}")
        
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


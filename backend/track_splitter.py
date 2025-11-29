import librosa
import soundfile as sf
import numpy as np
from pathlib import Path

class TrackSplitter:
    def __init__(self):
        self.silence_threshold = -40  # dB
        self.min_silence_duration = 2.0  # Sekunden
        self.min_track_duration = 10.0  # Sekunden
        
    def split_audio(self, audio_path: Path, output_dir: Path):
        """Erkenne Pausen und splitte Audio in Tracks"""
        print(f"Lade Audio: {audio_path}")
        
        # Prüfe Dateigröße
        file_size_mb = audio_path.stat().st_size / (1024 * 1024)
        print(f"Dateigröße: {file_size_mb:.2f} MB")
        
        if file_size_mb > 500:
            print("Warnung: Sehr große Datei, Verarbeitung kann länger dauern...")
        
        try:
            # Lade Audio mit Progress-Callback wäre ideal, aber librosa unterstützt das nicht direkt
            # Verwende sr=None um native Sample-Rate zu behalten
            print("Lade Audio-Datei...")
            y, sr = librosa.load(str(audio_path), sr=None, mono=False)
            print(f"Audio geladen: {y.shape} Shape, {sr} Hz")
            
            # Behalte Stereo-Information für Ausgabe
            is_stereo = len(y.shape) > 1 and y.shape[0] == 2
            
            # Für Silence-Erkennung: Konvertiere zu Mono (nur für Analyse)
            if is_stereo:
                print("Konvertiere Stereo zu Mono für Silence-Erkennung...")
                y_mono = librosa.to_mono(y)
            else:
                y_mono = y
        except Exception as e:
            print(f"Fehler beim Laden der Audio-Datei: {e}")
            import traceback
            traceback.print_exc()
            raise Exception(f"Fehler beim Laden der Audio-Datei: {e}")
        
        # Berechne RMS Energy (mit Mono für bessere Silence-Erkennung)
        print("Berechne RMS Energy...")
        frame_length = 2048
        hop_length = 512
        rms = librosa.feature.rms(y=y_mono, frame_length=frame_length, hop_length=hop_length)[0]
        
        # Konvertiere zu dB
        print("Konvertiere zu dB...")
        rms_db = librosa.power_to_db(rms**2, ref=np.max)
        
        # Finde Silence-Bereiche
        print(f"Suche Silence-Bereiche (Schwelle: {self.silence_threshold} dB)...")
        silence_mask = rms_db < self.silence_threshold
        
        # Finde längere Silence-Perioden
        silence_frames = librosa.frames_to_time(
            np.where(silence_mask)[0],
            sr=sr,
            hop_length=hop_length
        )
        
        # Gruppiere nahe Silence-Bereiche
        print("Analysiere Silence-Perioden...")
        split_points = [0.0]
        
        if len(silence_frames) == 0:
            print("Keine Silence-Bereiche gefunden - erstelle einen einzigen Track")
            # Bei Stereo: y.shape[1] ist die Anzahl der Samples
            total_duration = y.shape[1] / sr if is_stereo else len(y) / sr
            split_points.append(total_duration)
        else:
            last_silence_start = silence_frames[0]
            
            for i, silence_time in enumerate(silence_frames):
                if i == 0:
                    last_silence_start = silence_time
                    continue
                
                # Wenn Pause lang genug ist
                if silence_time - last_silence_start >= self.min_silence_duration:
                    # Split-Punkt in der Mitte der Pause
                    split_point = (last_silence_start + silence_time) / 2
                    
                    # Prüfe ob Track lang genug ist
                    if split_point - split_points[-1] >= self.min_track_duration:
                        split_points.append(split_point)
                        print(f"  Split-Punkt bei {split_point:.2f}s")
                    
                    last_silence_start = silence_time
            
            # Bei Stereo: y.shape[1] ist die Anzahl der Samples
            total_duration = y.shape[1] / sr if is_stereo else len(y) / sr
            split_points.append(total_duration)  # Ende
        
        print(f"Gefundene Split-Punkte: {len(split_points)} -> {len(split_points)-1} Tracks")
        
        # Erstelle Track-Dateien
        print("Erstelle Track-Dateien...")
        tracks = []
        base_name = audio_path.stem
        
        for i in range(len(split_points) - 1):
            start_time = split_points[i]
            end_time = split_points[i + 1]
            
            start_sample = int(start_time * sr)
            end_sample = int(end_time * sr)
            
            print(f"  Track {i+1}: {start_time:.2f}s - {end_time:.2f}s ({end_time-start_time:.2f}s)")
            
            # Verwende Stereo-Daten falls vorhanden, sonst Mono
            if is_stereo:
                track_audio = y[:, start_sample:end_sample].T  # Transponiere für soundfile Format (samples x channels)
            else:
                track_audio = y[start_sample:end_sample]
            
            track_filename = f"{base_name}_track_{i+1:02d}.flac"
            track_path = output_dir / track_filename
            
            try:
                # Speichere mit korrekter Kanalanzahl
                if is_stereo:
                    sf.write(str(track_path), track_audio, sr, format='FLAC', subtype='PCM_24')
                    print(f"    Gespeichert: {track_filename} (Stereo)")
                else:
                    sf.write(str(track_path), track_audio, sr, format='FLAC', subtype='PCM_24')
                    print(f"    Gespeichert: {track_filename} (Mono)")
            except Exception as e:
                print(f"    Fehler beim Speichern von {track_filename}: {e}")
                raise
            
            tracks.append({
                "filename": track_filename,
                "track_number": i + 1,
                "start_time": start_time,
                "end_time": end_time,
                "duration": end_time - start_time
            })
        
        print(f"Track-Splitting abgeschlossen: {len(tracks)} Tracks erstellt")
        return tracks


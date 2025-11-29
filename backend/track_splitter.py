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
        y, sr = librosa.load(str(audio_path), sr=None)
        
        # Berechne RMS Energy
        frame_length = 2048
        hop_length = 512
        rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
        
        # Konvertiere zu dB
        rms_db = librosa.power_to_db(rms**2, ref=np.max)
        
        # Finde Silence-Bereiche
        silence_mask = rms_db < self.silence_threshold
        
        # Finde längere Silence-Perioden
        silence_frames = librosa.frames_to_time(
            np.where(silence_mask)[0],
            sr=sr,
            hop_length=hop_length
        )
        
        # Gruppiere nahe Silence-Bereiche
        split_points = [0.0]
        last_silence_start = silence_frames[0] if len(silence_frames) > 0 else 0
        
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
                
                last_silence_start = silence_time
        
        split_points.append(len(y) / sr)  # Ende
        
        # Erstelle Track-Dateien
        tracks = []
        base_name = audio_path.stem
        
        for i in range(len(split_points) - 1):
            start_time = split_points[i]
            end_time = split_points[i + 1]
            
            start_sample = int(start_time * sr)
            end_sample = int(end_time * sr)
            
            track_audio = y[start_sample:end_sample]
            
            track_filename = f"{base_name}_track_{i+1:02d}.flac"
            track_path = output_dir / track_filename
            
            sf.write(str(track_path), track_audio, sr, format='FLAC')
            
            tracks.append({
                "filename": track_filename,
                "track_number": i + 1,
                "start_time": start_time,
                "end_time": end_time,
                "duration": end_time - start_time
            })
        
        return tracks


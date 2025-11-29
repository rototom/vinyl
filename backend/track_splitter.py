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
        """Erkenne Pausen und splitte Audio in Tracks (speichereffizient)"""
        print(f"Lade Audio: {audio_path}")
        
        # Prüfe Dateigröße
        file_size_mb = audio_path.stat().st_size / (1024 * 1024)
        print(f"Dateigröße: {file_size_mb:.2f} MB")
        
        if file_size_mb > 200:
            print("Warnung: Große Datei - verwende speichereffiziente Verarbeitung...")
        
        try:
            # Lade Metadaten der Datei
            with sf.SoundFile(str(audio_path)) as f:
                sr = f.samplerate
                channels = f.channels
                frames = f.frames
                duration = frames / sr
                is_stereo = channels == 2
            
            print(f"Audio-Info: {channels} Kanäle, {sr} Hz, {duration:.1f}s ({frames} Samples)")
            
            # Speichereffiziente RMS-Berechnung in Chunks
            print("Berechne RMS Energy (speichereffizient)...")
            frame_length = 2048
            hop_length = 512
            chunk_size = 44100 * 10  # 10 Sekunden pro Chunk
            
            rms_frames = []
            total_frames = 0
            
            with sf.SoundFile(str(audio_path)) as f:
                while True:
                    chunk = f.read(chunk_size, dtype='float32')
                    if len(chunk) == 0:
                        break
                    
                    # Konvertiere zu Mono für RMS-Berechnung
                    # soundfile gibt Daten im Format (samples, channels) zurück
                    if is_stereo:
                        # Transponiere zu (channels, samples) für librosa.to_mono
                        chunk_mono = librosa.to_mono(chunk.T)
                    else:
                        chunk_mono = chunk.flatten() if len(chunk.shape) > 1 else chunk
                    
                    # Berechne RMS für diesen Chunk
                    chunk_rms = librosa.feature.rms(
                        y=chunk_mono, 
                        frame_length=frame_length, 
                        hop_length=hop_length
                    )[0]
                    
                    rms_frames.append(chunk_rms)
                    total_frames += len(chunk_mono)
                    
                    if len(rms_frames) % 10 == 0:
                        progress = (f.tell() / frames) * 100
                        print(f"  Verarbeitet: {progress:.1f}%")
            
            # Kombiniere alle RMS-Frames
            rms = np.concatenate(rms_frames)
            print(f"RMS-Berechnung abgeschlossen: {len(rms)} Frames")
            
        except Exception as e:
            print(f"Fehler beim Laden der Audio-Datei: {e}")
            import traceback
            traceback.print_exc()
            raise Exception(f"Fehler beim Laden der Audio-Datei: {e}")
        
        # Konvertiere zu dB
        print("Konvertiere zu dB...")
        rms_db = librosa.power_to_db(rms**2, ref=np.max)
        
        # Finde Silence-Bereiche
        print(f"Suche Silence-Bereiche (Schwelle: {self.silence_threshold} dB, min. Dauer: {self.min_silence_duration}s)...")
        silence_mask = rms_db < self.silence_threshold
        
        # Finde kontinuierliche Silence-Perioden
        print("Analysiere kontinuierliche Silence-Perioden...")
        split_points = [0.0]
        
        # Finde Start- und Endpunkte von kontinuierlichen Silence-Bereichen
        silence_indices = np.where(silence_mask)[0]
        
        if len(silence_indices) == 0:
            print("Keine Silence-Bereiche gefunden - erstelle einen einzigen Track")
            # Verwende duration aus SoundFile
            with sf.SoundFile(str(audio_path)) as f:
                total_duration = f.frames / f.samplerate
            split_points.append(total_duration)
        else:
            # Finde kontinuierliche Bereiche (wo aufeinanderfolgende Indizes zusammen gehören)
            silence_regions = []
            region_start = silence_indices[0]
            
            for i in range(1, len(silence_indices)):
                # Wenn Lücke zwischen Indizes zu groß ist (> 1 Frame), ist es ein neuer Bereich
                if silence_indices[i] - silence_indices[i-1] > 1:
                    # Ende des vorherigen Bereichs
                    region_end = silence_indices[i-1]
                    silence_regions.append((region_start, region_end))
                    # Start eines neuen Bereichs
                    region_start = silence_indices[i]
            
            # Füge den letzten Bereich hinzu
            silence_regions.append((region_start, silence_indices[-1]))
            
            print(f"Gefunden: {len(silence_regions)} kontinuierliche Silence-Bereiche")
            
            # Konvertiere Frame-Indizes zu Zeitpunkten
            frame_times = librosa.frames_to_time(
                np.arange(len(silence_mask)),
                sr=sr,
                hop_length=hop_length
            )
            
            # Prüfe jeden Silence-Bereich auf Mindestdauer
            for region_start_idx, region_end_idx in silence_regions:
                start_time = frame_times[region_start_idx]
                end_time = frame_times[region_end_idx]
                duration = end_time - start_time
                
                # Nur wenn Stille lang genug ist
                if duration >= self.min_silence_duration:
                    # Split-Punkt in der Mitte der Stille
                    split_point = (start_time + end_time) / 2
                    
                    # Prüfe ob Track lang genug ist
                    if split_point - split_points[-1] >= self.min_track_duration:
                        split_points.append(split_point)
                        print(f"  Split-Punkt bei {split_point:.2f}s (Stille: {duration:.2f}s von {start_time:.2f}s bis {end_time:.2f}s)")
            
            # Verwende duration aus SoundFile
            with sf.SoundFile(str(audio_path)) as f:
                total_duration = f.frames / f.samplerate
            split_points.append(total_duration)  # Ende
        
        print(f"Gefundene Split-Punkte: {len(split_points)} -> {len(split_points)-1} Tracks")
        
        # Erstelle Track-Dateien (speichereffizient)
        print("Erstelle Track-Dateien...")
        tracks = []
        base_name = audio_path.stem
        
        for i in range(len(split_points) - 1):
            start_time = split_points[i]
            end_time = split_points[i + 1]
            
            start_frame = int(start_time * sr)
            end_frame = int(end_time * sr)
            
            print(f"  Track {i+1}: {start_time:.2f}s - {end_time:.2f}s ({end_time-start_time:.2f}s)")
            
            track_filename = f"{base_name}_track_{i+1:02d}.flac"
            track_path = output_dir / track_filename
            
            try:
                # Lese nur den benötigten Bereich aus der Datei
                with sf.SoundFile(str(audio_path)) as infile:
                    # Setze Position
                    infile.seek(start_frame)
                    # Lese nur die benötigten Frames
                    track_audio = infile.read(end_frame - start_frame, dtype='float32')
                    
                    # Speichere Track
                    sf.write(
                        str(track_path), 
                        track_audio, 
                        sr, 
                        format='FLAC', 
                        subtype='PCM_24'
                    )
                    
                    channel_info = "Stereo" if is_stereo else "Mono"
                    print(f"    Gespeichert: {track_filename} ({channel_info})")
            except Exception as e:
                print(f"    Fehler beim Speichern von {track_filename}: {e}")
                import traceback
                traceback.print_exc()
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


from mutagen.flac import FLAC, Picture
from pathlib import Path
from PIL import Image
import io

class AudioTagger:
    def tag_file(self, filepath: Path, title=None, artist=None, 
                 album=None, track_number=None, year=None, genre=None, 
                 cover_path=None, album_artist=None, disc_number=None, total_tracks=None):
        """Füge Metadaten zu FLAC-Datei hinzu"""
        audio = FLAC(str(filepath))
        
        if title:
            audio['TITLE'] = [title]
        if artist:
            audio['ARTIST'] = [artist]
        if album_artist:
            audio['ALBUMARTIST'] = [album_artist]
        if album:
            audio['ALBUM'] = [album]
        if track_number:
            audio['TRACKNUMBER'] = [str(track_number)]
        if total_tracks:
            audio['TRACKTOTAL'] = [str(total_tracks)]
        if disc_number:
            audio['DISCNUMBER'] = [str(disc_number)]
        if year:
            audio['DATE'] = [str(year)]
        if genre:
            audio['GENRE'] = [genre]
        
        # Füge Cover-Art hinzu
        if cover_path and Path(cover_path).exists():
            try:
                self._add_cover_art(audio, cover_path)
            except Exception as e:
                print(f"Fehler beim Hinzufügen des Covers: {e}")
        
        audio.save()
    
    def _add_cover_art(self, audio: FLAC, cover_path: Path):
        """Füge Cover-Art zu FLAC-Datei hinzu"""
        try:
            # Lade Bild
            image = Image.open(cover_path)
            
            # Konvertiere zu RGB falls nötig
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Resize falls zu groß (max 1000x1000)
            max_size = 1000
            if image.width > max_size or image.height > max_size:
                image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            
            # Speichere in Bytes
            img_bytes = io.BytesIO()
            image.save(img_bytes, format='JPEG', quality=90)
            img_bytes.seek(0)
            
            # Erstelle Picture-Objekt
            picture = Picture()
            picture.type = 3  # Front Cover
            picture.mime = 'image/jpeg'
            picture.data = img_bytes.read()
            picture.width = image.width
            picture.height = image.height
            
            # Füge zu FLAC hinzu
            audio.add_picture(picture)
            
        except Exception as e:
            print(f"Fehler beim Verarbeiten des Covers: {e}")
            raise


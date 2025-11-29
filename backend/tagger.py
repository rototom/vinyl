from mutagen.flac import FLAC
from pathlib import Path

class AudioTagger:
    def tag_file(self, filepath: Path, title=None, artist=None, 
                 album=None, track_number=None, year=None, genre=None):
        """Füge Metadaten zu FLAC-Datei hinzu"""
        audio = FLAC(str(filepath))
        
        if title:
            audio['TITLE'] = [title]
        if artist:
            audio['ARTIST'] = [artist]
        if album:
            audio['ALBUM'] = [album]
        if track_number:
            audio['TRACKNUMBER'] = [str(track_number)]
        if year:
            audio['DATE'] = [str(year)]
        if genre:
            audio['GENRE'] = [genre]
        
        audio.save()


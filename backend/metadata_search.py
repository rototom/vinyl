import requests
import json
from typing import List, Dict, Optional, Any
from pathlib import Path
import time

class MetadataSearcher:
    """Sucht nach Album-Metadaten über MusicBrainz API"""
    
    def __init__(self):
        self.musicbrainz_base = "https://musicbrainz.org/ws/2"
        self.coverart_base = "https://coverartarchive.org"
        self.headers = {
            "User-Agent": "VinylDigitalizer/1.0 (https://github.com/rototom/vinyl)",
            "Accept": "application/json"
        }
    
    def search_album(self, artist: str, album: str) -> List[Dict[str, Any]]:
        """Suche nach Album in MusicBrainz"""
        try:
            # MusicBrainz-Suche
            query = f'artist:"{artist}" AND release:"{album}"'
            url = f"{self.musicbrainz_base}/release"
            params = {
                "query": query,
                "fmt": "json",
                "limit": 10
            }
            
            print(f"Suche MusicBrainz: {query}")
            response = requests.get(url, params=params, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            releases = []
            
            for release in data.get("releases", []):
                release_info = {
                    "mbid": release.get("id"),
                    "title": release.get("title"),
                    "artist": release.get("artist-credit", [{}])[0].get("name", "") if release.get("artist-credit") else "",
                    "date": release.get("date", ""),
                    "country": release.get("country", ""),
                    "track_count": release.get("track-count", 0),
                    "media": []
                }
                
                # Hole detaillierte Informationen
                try:
                    detail_url = f"{self.musicbrainz_base}/release/{release_info['mbid']}"
                    detail_params = {
                        "inc": "recordings+media",
                        "fmt": "json"
                    }
                    detail_response = requests.get(detail_url, params=detail_params, headers=self.headers, timeout=10)
                    detail_response.raise_for_status()
                    detail_data = detail_response.json()
                    
                    # Extrahiere Media-Informationen (LP-Seiten)
                    for medium in detail_data.get("media", []):
                        medium_info = {
                            "position": medium.get("position", 1),
                            "format": medium.get("format", ""),
                            "track_count": medium.get("track-count", 0),
                            "tracks": []
                        }
                        
                        for track in medium.get("tracks", []):
                            track_info = {
                                "position": track.get("position", 0),
                                "title": track.get("title", ""),
                                "length": track.get("length", 0)  # in Millisekunden
                            }
                            medium_info["tracks"].append(track_info)
                        
                        release_info["media"].append(medium_info)
                    
                    # Hole Cover-Art
                    try:
                        cover_url = f"{self.coverart_base}/release/{release_info['mbid']}"
                        cover_response = requests.get(cover_url, headers=self.headers, timeout=5)
                        if cover_response.status_code == 200:
                            cover_data = cover_response.json()
                            images = cover_data.get("images", [])
                            if images:
                                # Verwende erstes Front-Cover oder erstes Bild
                                front_cover = next((img for img in images if img.get("front", False)), images[0])
                                release_info["cover_url"] = front_cover.get("image", "")
                    except Exception as e:
                        print(f"Fehler beim Laden des Covers: {e}")
                    
                    # Rate-Limiting: MusicBrainz erlaubt max 1 Request pro Sekunde
                    time.sleep(1.1)
                    
                except Exception as e:
                    print(f"Fehler beim Laden der Details für {release_info['mbid']}: {e}")
                    continue
                
                releases.append(release_info)
            
            return releases
            
        except Exception as e:
            print(f"Fehler bei MusicBrainz-Suche: {e}")
            return []
    
    def match_album(self, found_tracks: List[Dict], album_releases: List[Dict], 
                   total_duration: float, tracks_per_side: Optional[int] = None) -> Optional[Dict]:
        """Finde das beste passende Album basierend auf Track-Anzahl und Länge"""
        best_match = None
        best_score = 0
        
        for release in album_releases:
            score = 0
            
            # Prüfe Track-Anzahl pro Medium (LP-Seite)
            if release.get("media"):
                for medium in release["media"]:
                    medium_track_count = medium.get("track_count", 0)
                    
                    # Wenn tracks_per_side angegeben ist, vergleiche damit
                    if tracks_per_side:
                        if medium_track_count == tracks_per_side:
                            score += 50
                        elif abs(medium_track_count - tracks_per_side) <= 1:
                            score += 30
                    else:
                        # Vergleiche mit gefundenen Tracks
                        if medium_track_count == len(found_tracks):
                            score += 50
                        elif abs(medium_track_count - len(found_tracks)) <= 1:
                            score += 30
                    
                    # Prüfe Gesamtlänge der Tracks im Medium
                    medium_duration = sum(t.get("length", 0) / 1000.0 for t in medium.get("tracks", []))
                    if medium_duration > 0:
                        duration_diff = abs(medium_duration - total_duration)
                        duration_ratio = duration_diff / total_duration if total_duration > 0 else 1
                        if duration_ratio < 0.1:  # Weniger als 10% Unterschied
                            score += 40
                        elif duration_ratio < 0.2:  # Weniger als 20% Unterschied
                            score += 20
            
            # Bonus für Vinyl-Format
            if any(m.get("format", "").lower() in ["vinyl", "12\"", "lp"] for m in release.get("media", [])):
                score += 10
            
            if score > best_score:
                best_score = score
                best_match = release
        
        return best_match if best_score >= 30 else None  # Mindest-Score von 30
    
    def download_cover(self, cover_url: str, output_path: Path):
        """Lade Cover-Art herunter"""
        try:
            response = requests.get(cover_url, timeout=10)
            response.raise_for_status()
            output_path.write_bytes(response.content)
            return True
        except Exception as e:
            print(f"Fehler beim Download des Covers: {e}")
            return False


// API-Base-URL dynamisch basierend auf aktuellem Host
const getApiBase = () => {
    const protocol = window.location.protocol === 'https:' ? 'https:' : 'http:';
    const host = window.location.hostname;
    const port = window.location.port || '8045';
    return `${protocol}//${host}:${port}/api`;
};

const API_BASE = getApiBase();
let ws = null;
let recordings = [];
let waveformCanvas = null;
let waveformCtx = null;
let waveformData = [];
let currentAudioPlayer = null;

// WebSocket für Audio-Level
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.hostname;
    const port = window.location.port || '8045';
    const wsUrl = `${protocol}//${host}:${port}/ws`;
    
    ws = new WebSocket(wsUrl);
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'level') {
            updateLevelBar(data.value);
        }
    };
    
    ws.onerror = () => {
        setTimeout(connectWebSocket, 1000);
    };
    
    ws.onclose = () => {
        setTimeout(connectWebSocket, 1000);
    };
}

function updateLevelBar(level) {
    const percentage = Math.min(level * 100, 100);
    document.getElementById('levelBar').style.width = percentage + '%';
    document.getElementById('levelText').textContent = 
        `Level: ${percentage.toFixed(1)}%`;
    
    // Waveform aktualisieren
    updateWaveform(level);
}

function initWaveform() {
    waveformCanvas = document.getElementById('waveformCanvas');
    if (waveformCanvas) {
        waveformCtx = waveformCanvas.getContext('2d');
        waveformCanvas.width = waveformCanvas.offsetWidth;
        waveformCanvas.height = waveformCanvas.offsetHeight;
    }
}

function updateWaveform(level) {
    if (!waveformCanvas || !waveformCtx) return;
    
    const isRecording = document.getElementById('stopBtn').disabled === false;
    if (!isRecording) {
        waveformCanvas.style.display = 'none';
        waveformData = [];
        return;
    }
    
    waveformCanvas.style.display = 'block';
    
    // Füge neuen Datenpunkt hinzu
    waveformData.push(level);
    
    // Begrenze auf Canvas-Breite
    const maxPoints = waveformCanvas.width / 2;
    if (waveformData.length > maxPoints) {
        waveformData.shift();
    }
    
    // Zeichne Waveform
    waveformCtx.clearRect(0, 0, waveformCanvas.width, waveformCanvas.height);
    waveformCtx.strokeStyle = '#60a5fa';
    waveformCtx.lineWidth = 2;
    waveformCtx.beginPath();
    
    const centerY = waveformCanvas.height / 2;
    const stepX = waveformCanvas.width / waveformData.length;
    
    waveformData.forEach((value, index) => {
        const x = index * stepX;
        const amplitude = value * waveformCanvas.height * 0.4;
        const y = centerY - amplitude;
        
        if (index === 0) {
            waveformCtx.moveTo(x, y);
        } else {
            waveformCtx.lineTo(x, y);
        }
    });
    
    waveformCtx.stroke();
    
    // Zeichne auch untere Hälfte (gespiegelt)
    waveformCtx.beginPath();
    waveformData.forEach((value, index) => {
        const x = index * stepX;
        const amplitude = value * waveformCanvas.height * 0.4;
        const y = centerY + amplitude;
        
        if (index === 0) {
            waveformCtx.moveTo(x, y);
        } else {
            waveformCtx.lineTo(x, y);
        }
    });
    waveformCtx.stroke();
}

// Aufnahme starten
document.getElementById('startBtn').addEventListener('click', async () => {
    try {
        const response = await fetch(`${API_BASE}/start-recording`, {
            method: 'POST'
        });
        const data = await response.json();
        
        if (response.ok) {
            document.getElementById('startBtn').disabled = true;
            document.getElementById('stopBtn').disabled = false;
            document.getElementById('recordingStatus').textContent = 
                `Aufnahme läuft: ${data.filename}`;
        } else {
            alert('Fehler: ' + data.error);
        }
    } catch (error) {
        alert('Fehler beim Starten der Aufnahme: ' + error.message);
    }
});

// Aufnahme stoppen
document.getElementById('stopBtn').addEventListener('click', async () => {
    try {
        const response = await fetch(`${API_BASE}/stop-recording`, {
            method: 'POST'
        });
        const data = await response.json();
        
        if (response.ok) {
            document.getElementById('startBtn').disabled = false;
            document.getElementById('stopBtn').disabled = true;
            document.getElementById('recordingStatus').textContent = 
                `Aufnahme gespeichert: ${data.filename}`;
            loadRecordings();
        } else {
            alert('Fehler: ' + data.error);
        }
    } catch (error) {
        alert('Fehler beim Stoppen der Aufnahme: ' + error.message);
    }
});

// Aufnahmen laden
async function loadRecordings() {
    try {
        const response = await fetch(`${API_BASE}/recordings`);
        const data = await response.json();
        recordings = data.recordings;
        
        displayRecordings();
        updateSelects();
    } catch (error) {
        console.error('Fehler beim Laden der Aufnahmen:', error);
    }
}

function displayRecordings() {
    const list = document.getElementById('recordingsList');
    list.innerHTML = '';
    
    if (recordings.length === 0) {
        list.innerHTML = '<p class="text-gray-300">Keine Aufnahmen vorhanden</p>';
        return;
    }
    
    recordings.forEach(rec => {
        const sizeMB = (rec.size / 1024 / 1024).toFixed(2);
        const date = new Date(rec.created * 1000).toLocaleString('de-DE');
        const audioUrl = `${API_BASE.replace('/api', '')}/api/audio/${rec.filename}`;
        const downloadUrl = `${API_BASE.replace('/api', '')}/api/download/${rec.filename}`;
        
        const div = document.createElement('div');
        div.className = 'bg-gray-800 rounded-lg p-4';
        div.innerHTML = `
            <div class="flex justify-between items-start mb-3">
                <div class="flex-1">
                    <p class="text-white font-semibold">${rec.filename}</p>
                    <p class="text-gray-400 text-sm">${sizeMB} MB • ${date}</p>
                </div>
                <button onclick="deleteRecording('${rec.filename}')" 
                        class="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg ml-2">
                    Löschen
                </button>
            </div>
            <div class="flex items-center space-x-2">
                <audio controls class="flex-1" preload="metadata">
                    <source src="${audioUrl}" type="audio/flac">
                    Dein Browser unterstützt kein Audio-Element.
                </audio>
                <a href="${downloadUrl}" download="${rec.filename}" 
                   class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg whitespace-nowrap">
                    ⬇ Download
                </a>
            </div>
        `;
        list.appendChild(div);
    });
}

function updateSelects() {
    const recordingSelect = document.getElementById('recordingSelect');
    recordingSelect.innerHTML = '<option value="">-- Auswählen --</option>';
    recordings.forEach(rec => {
        const option = document.createElement('option');
        option.value = rec.filename;
        option.textContent = rec.filename;
        recordingSelect.appendChild(option);
    });
    
    if (recordings.length > 0) {
        document.getElementById('splitSection').classList.remove('hidden');
    }
}

// Track-Splitting
document.getElementById('splitBtn').addEventListener('click', async () => {
    const filename = document.getElementById('recordingSelect').value;
    if (!filename) {
        alert('Bitte wählen Sie eine Aufnahme aus');
        return;
    }
    
    const splitBtn = document.getElementById('splitBtn');
    const originalText = splitBtn.textContent;
    
    try {
        const formData = new FormData();
        formData.append('filename', filename);
        
        splitBtn.disabled = true;
        splitBtn.textContent = '⏳ Verarbeitung... (dies kann bei großen Dateien einige Minuten dauern)';
        
        // Erstelle AbortController für Timeout
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 600000); // 10 Minuten Timeout
        
        const response = await fetch(`${API_BASE}/split-tracks`, {
            method: 'POST',
            body: formData,
            signal: controller.signal
        });
        
        clearTimeout(timeoutId);
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ error: 'Unbekannter Fehler' }));
            throw new Error(errorData.error || `HTTP ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.tracks && data.tracks.length > 0) {
            displayTracks(data.tracks);
            updateTrackSelect(data.tracks);
            document.getElementById('tagSection').classList.remove('hidden');
            document.getElementById('metadataSearchSection').classList.remove('hidden');
            splitBtn.textContent = `✅ ${data.tracks.length} Tracks erstellt`;
        } else {
            throw new Error('Keine Tracks erstellt');
        }
        
    } catch (error) {
        if (error.name === 'AbortError') {
            alert('Verarbeitung dauerte zu lange (Timeout nach 10 Minuten). Bitte versuchen Sie es mit einer kleineren Datei oder kontaktieren Sie den Support.');
        } else {
            alert('Fehler beim Splitting: ' + error.message);
        }
        splitBtn.textContent = originalText;
    } finally {
        splitBtn.disabled = false;
        // Setze Text nach 3 Sekunden zurück
        setTimeout(() => {
            if (splitBtn.textContent.includes('✅')) {
                splitBtn.textContent = originalText;
            }
        }, 3000);
    }
});

function displayTracks(tracks) {
    const list = document.getElementById('tracksList');
    list.innerHTML = '';
    
    if (tracks.length === 0) {
        list.innerHTML = '<p class="text-gray-300">Keine Tracks gefunden</p>';
        return;
    }
    
    // Album-Download-Button hinzufügen
    if (tracks.length > 0) {
        const baseFilename = tracks[0].filename.split('_track_')[0];
        const albumDiv = document.createElement('div');
        albumDiv.className = 'bg-indigo-900/50 rounded-lg p-4 mb-4 border border-indigo-600';
        albumDiv.innerHTML = `
            <div class="flex justify-between items-center">
                <div>
                    <p class="text-white font-semibold">📀 Album: ${baseFilename}</p>
                    <p class="text-gray-400 text-sm">${tracks.length} Tracks</p>
                </div>
                <a href="${API_BASE.replace('/api', '')}/api/download-album/${tracks[0].filename}" 
                   class="bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-2 rounded-lg">
                    ⬇ Album herunterladen (ZIP)
                </a>
            </div>
        `;
        list.appendChild(albumDiv);
    }
    
    tracks.forEach(track => {
        const duration = formatTime(track.duration);
        const audioUrl = `${API_BASE.replace('/api', '')}/api/audio/${track.filename}`;
        const downloadUrl = `${API_BASE.replace('/api', '')}/api/download/${track.filename}`;
        
        const div = document.createElement('div');
        div.className = 'bg-gray-800 rounded-lg p-4 mb-3';
        div.innerHTML = `
            <div class="mb-3">
                <p class="text-white font-semibold">Track ${track.track_number}: ${track.filename}</p>
                <p class="text-gray-400 text-sm">Dauer: ${duration} • ${(track.start_time / 60).toFixed(1)}min - ${(track.end_time / 60).toFixed(1)}min</p>
            </div>
            <div class="flex items-center space-x-2">
                <audio controls class="flex-1" preload="metadata">
                    <source src="${audioUrl}" type="audio/flac">
                    Dein Browser unterstützt kein Audio-Element.
                </audio>
                <a href="${downloadUrl}" download="${track.filename}" 
                   class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg whitespace-nowrap">
                    ⬇ Download
                </a>
            </div>
        `;
        list.appendChild(div);
    });
}

function updateTrackSelect(tracks) {
    const trackSelect = document.getElementById('trackSelect');
    trackSelect.innerHTML = '';
    
    tracks.forEach(track => {
        const option = document.createElement('option');
        option.value = track.filename;
        option.textContent = `Track ${track.track_number}: ${track.filename}`;
        option.dataset.trackNumber = track.track_number;
        trackSelect.appendChild(option);
    });
    
    // Auto-fill track number when selection changes
    trackSelect.addEventListener('change', (e) => {
        const selectedOption = e.target.options[e.target.selectedIndex];
        if (selectedOption.dataset.trackNumber) {
            document.getElementById('trackNumInput').value = selectedOption.dataset.trackNumber;
        }
    });
}

// Tagging
document.getElementById('tagForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const formData = new FormData();
    formData.append('filename', document.getElementById('trackSelect').value);
    formData.append('title', document.getElementById('titleInput').value);
    formData.append('artist', document.getElementById('artistInput').value);
    formData.append('album', document.getElementById('albumInput').value);
    formData.append('track_number', document.getElementById('trackNumInput').value);
    
    try {
        const response = await fetch(`${API_BASE}/tag-track`, {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (response.ok) {
            alert('Metadaten erfolgreich gespeichert!');
            document.getElementById('tagForm').reset();
            loadRecordings();
        } else {
            alert('Fehler: ' + data.error);
        }
    } catch (error) {
        alert('Fehler beim Speichern: ' + error.message);
    }
});

// Aufnahme löschen
async function deleteRecording(filename) {
    if (!confirm(`Möchten Sie "${filename}" wirklich löschen?`)) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/delete/${filename}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            loadRecordings();
        } else {
            alert('Fehler beim Löschen');
        }
    } catch (error) {
        alert('Fehler: ' + error.message);
    }
}

function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// Einstellungen laden
async function loadSettings() {
    try {
        const response = await fetch(`${API_BASE}/settings`);
        const settings = await response.json();
        
        // Audio-Gerät
        const deviceSelect = document.getElementById('audioDeviceSelect');
        const statusResponse = await fetch(`${API_BASE}/status`);
        const status = await statusResponse.json();
        
        deviceSelect.innerHTML = '<option value="-1">Standard-Gerät</option>';
        if (status.devices) {
            status.devices.forEach(device => {
                const option = document.createElement('option');
                option.value = device.index;
                option.textContent = `${device.index}: ${device.name} (${device.channels} Kanäle)`;
                if (device.index === status.current_device_index) {
                    option.selected = true;
                }
                deviceSelect.appendChild(option);
            });
        }
        
        // ALSA-Geräte
        const alsaSelect = document.getElementById('alsaDeviceSelect');
        const alsaSection = document.getElementById('alsaDeviceSection');
        const alsaInfo = document.getElementById('alsaInfo');
        
        if (status.use_alsa) {
            alsaSection.classList.remove('hidden');
            alsaInfo.textContent = 'ALSA-Recorder wird verwendet (PyAudio hat keine Input-Geräte gefunden)';
            alsaInfo.className = 'text-yellow-400 text-sm mt-1';
        } else {
            alsaSection.classList.add('hidden');
        }
        
        alsaSelect.innerHTML = '<option value="">-- Auswählen --</option>';
        if (status.alsa_devices && status.alsa_devices.length > 0) {
            status.alsa_devices.forEach(device => {
                const option = document.createElement('option');
                option.value = device.alsa_id || device.alsa_id;
                option.textContent = `${device.name} (${device.alsa_id || device.alsa_id})`;
                if (status.current_device === (device.alsa_id || device.alsa_id)) {
                    option.selected = true;
                }
                alsaSelect.appendChild(option);
            });
        }
        
        // Audio-Einstellungen
        if (settings.audio) {
            document.getElementById('sampleRateSelect').value = settings.audio.sample_rate || 44100;
            document.getElementById('channelsSelect').value = settings.audio.channels || 2;
            
            // ALSA-Gerät setzen
            if (settings.audio.alsa_device) {
                const alsaSelect = document.getElementById('alsaDeviceSelect');
                alsaSelect.value = settings.audio.alsa_device;
            }
        }
        
        // Naming-Einstellungen
        if (settings.naming) {
            document.getElementById('namingPattern').value = settings.naming.pattern || '{date}';
            document.getElementById('useTimestamp').checked = settings.naming.use_timestamp !== false;
        }
        
        // Recording-Einstellungen
        if (settings.recording) {
            document.getElementById('silenceThreshold').value = settings.recording.silence_threshold_db || -40;
            document.getElementById('minSilenceDuration').value = settings.recording.min_silence_duration || 2.0;
            document.getElementById('minTrackDuration').value = settings.recording.min_track_duration || 10.0;
        }
    } catch (error) {
        console.error('Fehler beim Laden der Einstellungen:', error);
    }
}

// Einstellungen speichern
document.getElementById('settingsForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const formData = new FormData(e.target);
    
    // Konvertiere Checkbox-Wert
    const useTimestamp = document.getElementById('useTimestamp').checked;
    
    const settingsData = new FormData();
    const deviceIndex = parseInt(formData.get('audio_device_index'));
    settingsData.append('audio_device_index', deviceIndex);
    
    // ALSA-Gerät
    const alsaDevice = formData.get('audio_alsa_device');
    if (alsaDevice) {
        settingsData.append('audio_alsa_device', alsaDevice);
    }
    
    settingsData.append('audio_sample_rate', parseInt(formData.get('audio_sample_rate')));
    settingsData.append('audio_channels', parseInt(formData.get('audio_channels')));
    settingsData.append('naming_pattern', formData.get('naming_pattern'));
    settingsData.append('naming_use_timestamp', useTimestamp);
    settingsData.append('recording_silence_threshold', parseFloat(formData.get('recording_silence_threshold')));
    settingsData.append('recording_min_silence_duration', parseFloat(formData.get('recording_min_silence_duration')));
    settingsData.append('recording_min_track_duration', parseFloat(formData.get('recording_min_track_duration')));
    
    try {
        const response = await fetch(`${API_BASE}/settings`, {
            method: 'POST',
            body: settingsData
        });
        
        const data = await response.json();
        
        if (response.ok) {
            alert('✅ Einstellungen erfolgreich gespeichert!');
            // Gerät neu laden
            loadSettings();
        } else {
            alert('Fehler: ' + data.error);
        }
    } catch (error) {
        alert('Fehler beim Speichern: ' + error.message);
    }
});

// Album-Suche
document.getElementById('searchAlbumForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const artist = document.getElementById('searchArtist').value;
    const album = document.getElementById('searchAlbum').value;
    const resultsDiv = document.getElementById('albumSearchResults');
    
    resultsDiv.innerHTML = '<p class="text-white">Suche...</p>';
    resultsDiv.classList.remove('hidden');
    
    try {
        const formData = new FormData();
        formData.append('artist', artist);
        formData.append('album', album);
        
        const response = await fetch(`${API_BASE}/search-album`, {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (response.ok && data.releases && data.releases.length > 0) {
            displayAlbumSearchResults(data.releases, artist, album);
        } else {
            resultsDiv.innerHTML = '<p class="text-red-400">Keine Alben gefunden. Versuche andere Suchbegriffe.</p>';
        }
    } catch (error) {
        resultsDiv.innerHTML = `<p class="text-red-400">Fehler bei der Suche: ${error.message}</p>`;
    }
});

function displayAlbumSearchResults(releases, searchArtist, searchAlbum) {
    const resultsDiv = document.getElementById('albumSearchResults');
    resultsDiv.innerHTML = '';
    
    releases.forEach((release, index) => {
        const totalTracks = release.track_count || 0;
        const mediaInfo = release.media && release.media.length > 0 ? 
            release.media.map(m => `Seite ${m.position}: ${m.track_count} Tracks`).join(', ') : 
            `${totalTracks} Tracks gesamt`;
        const coverImg = release.cover_url ? 
            `<img src="${release.cover_url}" alt="Cover" class="w-32 h-32 object-cover rounded-lg">` : 
            '<div class="w-32 h-32 bg-gray-700 rounded-lg flex items-center justify-center text-gray-400">Kein Cover</div>';
        
        const div = document.createElement('div');
        div.className = 'bg-gray-800 rounded-lg p-4 border border-gray-700 mb-3';
        div.innerHTML = `
            <div class="flex space-x-4">
                <div class="flex-shrink-0">
                    ${coverImg}
                </div>
                <div class="flex-1">
                    <h3 class="text-white font-bold text-lg">${release.title}</h3>
                    <p class="text-gray-300">${release.artist}</p>
                    <p class="text-gray-400 text-sm mt-2">
                        ${release.date ? `Jahr: ${release.date} • ` : ''}
                        ${totalTracks} Tracks gesamt<br>
                        ${mediaInfo}
                    </p>
                    <button onclick="selectAlbum('${release.mbid}', ${JSON.stringify(release.title)}, ${totalTracks})" 
                            class="mt-3 bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg">
                        ✅ Dieses Album verwenden
                    </button>
                </div>
            </div>
        `;
        resultsDiv.appendChild(div);
    });
}

async function selectAlbum(mbid, albumTitle, trackCount) {
    const recordingSelect = document.getElementById('recordingSelect');
    const filename = recordingSelect.value;
    
    if (!filename) {
        alert('Bitte wählen Sie zuerst eine Aufnahme aus');
        return;
    }
    
    const tracksPerSide = document.getElementById('tracksPerSide').value;
    
    if (!confirm(`Metadaten von "${albumTitle}" auf alle Tracks anwenden?`)) {
        return;
    }
    
    try {
        const formData = new FormData();
        formData.append('base_filename', filename);
        formData.append('release_mbid', mbid);
        if (tracksPerSide) {
            formData.append('tracks_per_side', tracksPerSide);
        }
        
        const response = await fetch(`${API_BASE}/auto-tag-album`, {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (response.ok) {
            alert(`✅ ${data.tagged_tracks} Tracks wurden erfolgreich getaggt!\nAlbum: ${data.album}\nInterpret: ${data.artist}`);
            loadRecordings();
        } else {
            alert('Fehler: ' + data.error);
        }
    } catch (error) {
        alert('Fehler beim Tagging: ' + error.message);
    }
}

// Initialisierung
initWaveform();
connectWebSocket();
loadRecordings();
loadSettings();
setInterval(loadRecordings, 5000); // Alle 5 Sekunden aktualisieren


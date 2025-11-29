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
let albums = {};
let waveformCanvas = null;
let waveformCtx = null;
let waveformData = [];
let currentAudioPlayer = null;
let isRecording = false;
let recordingFilename = null;
let statusCheckInterval = null;

// Tab-Navigation
function initTabs() {
    const tabs = {
        'tabRecord': 'contentRecord',
        'tabAlbums': 'contentAlbums',
        'tabSettings': 'contentSettings'
    };
    
    Object.keys(tabs).forEach(tabId => {
        const tabBtn = document.getElementById(tabId);
        const contentId = tabs[tabId];
        
        tabBtn.addEventListener('click', () => {
            // Alle Tabs deaktivieren
            document.querySelectorAll('.tab-btn').forEach(btn => {
                btn.classList.remove('tab-active');
                btn.classList.add('text-white/70');
            });
            
            // Alle Inhalte verstecken
            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.add('hidden');
            });
            
            // Aktiven Tab aktivieren
            tabBtn.classList.add('tab-active');
            tabBtn.classList.remove('text-white/70');
            document.getElementById(contentId).classList.remove('hidden');
            
            // Spezielle Aktionen pro Tab
            if (contentId === 'contentAlbums') {
                loadAlbums();
            }
        });
    });
}

// WebSocket für Audio-Level
const DELETE_CONFIRM_KEY = 'vinyl-confirm-delete';
const confirmDeleteCheckbox = document.getElementById('confirmDeleteCheckbox');
let confirmDeletes = localStorage.getItem(DELETE_CONFIRM_KEY);
confirmDeletes = confirmDeletes === null ? true : confirmDeletes === 'true';

if (confirmDeleteCheckbox) {
    confirmDeleteCheckbox.checked = confirmDeletes;
    confirmDeleteCheckbox.addEventListener('change', (event) => {
        confirmDeletes = event.target.checked;
        localStorage.setItem(DELETE_CONFIRM_KEY, confirmDeletes);
    });
}

function confirmAction(message) {
    if (!confirmDeletes) {
        return true;
    }
    return confirm(message);
}

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
            // Waveform nur aktualisieren wenn Aufnahme läuft
            if (isRecording) {
                updateWaveform(data.value);
            }
        }
    };
    
    ws.onerror = () => {
        setTimeout(connectWebSocket, 1000);
    };
    
    ws.onclose = () => {
        // Wenn Aufnahme läuft, versuche sofort wieder zu verbinden
        if (isRecording) {
            setTimeout(connectWebSocket, 500);
        } else {
            setTimeout(connectWebSocket, 1000);
        }
    };
}

function updateLevelBar(level) {
    const percentage = Math.min(level * 100, 100);
    const levelBar = document.getElementById('levelBar');
    const levelText = document.getElementById('levelText');
    
    if (levelBar) {
        levelBar.style.width = percentage + '%';
    }
    if (levelText) {
        levelText.textContent = `Level: ${percentage.toFixed(1)}%`;
    }
}

function initWaveform() {
    waveformCanvas = document.getElementById('waveformCanvas');
    if (waveformCanvas) {
        waveformCtx = waveformCanvas.getContext('2d');
        waveformCanvas.width = waveformCanvas.offsetWidth;
        waveformCanvas.height = waveformCanvas.offsetHeight;
        
        window.addEventListener('resize', () => {
            waveformCanvas.width = waveformCanvas.offsetWidth;
            waveformCanvas.height = waveformCanvas.offsetHeight;
            drawWaveform();
        });
    }
}

function updateWaveform(level) {
    if (!waveformCanvas || !waveformCtx) return;
    
    // Zeige Waveform immer während Aufnahme läuft
    if (isRecording) {
        waveformCanvas.style.display = 'block';
        waveformData.push(level);
        
        const maxPoints = Math.floor(waveformCanvas.width / 2);
        if (waveformData.length > maxPoints) {
            waveformData.shift();
        }
        
        drawWaveform();
    } else {
        // Waveform nur ausblenden wenn wirklich keine Aufnahme läuft
        waveformCanvas.style.display = 'none';
        waveformData = [];
    }
}

function drawWaveform() {
    if (!waveformCtx || waveformData.length === 0) return;
    
    waveformCtx.clearRect(0, 0, waveformCanvas.width, waveformCanvas.height);
    waveformCtx.strokeStyle = '#60a5fa';
    waveformCtx.lineWidth = 2;
    
    const centerY = waveformCanvas.height / 2;
    const stepX = waveformCanvas.width / waveformData.length;
    
    // Obere Hälfte
    waveformCtx.beginPath();
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
    
    // Untere Hälfte (gespiegelt)
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

// Update UI basierend auf Aufnahme-Status
function updateRecordingUI(status) {
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');
    const recordingStatus = document.getElementById('recordingStatus');
    
    const wasRecording = isRecording;
    isRecording = status.recording || false;
    recordingFilename = status.recording_filename || null;
    
    if (isRecording) {
        // Aufnahme läuft: Start-Button ausblenden, Stop-Button aktivieren
        startBtn.style.display = 'none';
        stopBtn.disabled = false;
        stopBtn.style.display = 'block';
        recordingStatus.textContent = `🎙️ Aufnahme läuft: ${recordingFilename || 'Unbekannt'}`;
        recordingStatus.className = 'text-center text-green-400 text-lg font-semibold';
        
        // Waveform anzeigen (auch wenn WebSocket noch nicht verbunden ist)
        if (waveformCanvas) {
            waveformCanvas.style.display = 'block';
            // Wenn gerade erst gestartet wurde, zeige leere Waveform
            if (!wasRecording && waveformData.length === 0) {
                drawWaveform();
            }
        }
    } else {
        // Keine Aufnahme: Start-Button anzeigen, Stop-Button deaktivieren
        startBtn.style.display = 'block';
        startBtn.disabled = false;
        stopBtn.disabled = true;
        stopBtn.style.display = 'block';
        
        // Status nur löschen wenn wirklich gestoppt wurde
        if (wasRecording) {
            recordingStatus.textContent = '';
        }
        
        // Waveform ausblenden nur wenn wirklich keine Aufnahme mehr läuft
        if (!isRecording && waveformCanvas) {
            waveformCanvas.style.display = 'none';
            waveformData = [];
        }
    }
}

// Prüfe regelmäßig den Aufnahme-Status
async function checkRecordingStatus() {
    try {
        const response = await fetch(`${API_BASE}/status`);
        const status = await response.json();
        updateRecordingUI(status);
        
        // Wenn Aufnahme läuft aber WebSocket nicht verbunden, versuche zu verbinden
        if (status.recording && (!ws || ws.readyState !== WebSocket.OPEN)) {
            connectWebSocket();
        }
    } catch (error) {
        console.error('Fehler beim Prüfen des Status:', error);
    }
}

// Aufnahme starten
document.getElementById('startBtn').addEventListener('click', async () => {
    try {
        const response = await fetch(`${API_BASE}/start-recording`, { method: 'POST' });
        const data = await response.json();
        
        if (response.ok) {
            // UI wird durch checkRecordingStatus aktualisiert
            await checkRecordingStatus();
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
        const response = await fetch(`${API_BASE}/stop-recording`, { method: 'POST' });
        const data = await response.json();
        
        if (response.ok) {
            // UI wird durch checkRecordingStatus aktualisiert
            await checkRecordingStatus();
            document.getElementById('recordingStatus').textContent = `✅ Aufnahme gespeichert: ${data.filename}`;
            document.getElementById('recordingStatus').className = 'text-center text-green-400 text-lg font-semibold';
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
        recordings = data.recordings || [];
        displayRecordings();
        updateSelects();
    } catch (error) {
        console.error('Fehler beim Laden der Aufnahmen:', error);
    }
}

function displayRecordings() {
    const list = document.getElementById('recordingsList');
    if (!list) return;
    
    list.innerHTML = '';
    
    if (recordings.length === 0) {
        list.innerHTML = '<p class="text-gray-400 text-center py-8">Keine Aufnahmen vorhanden</p>';
        return;
    }
    
    recordings.forEach(rec => {
        const sizeMB = (rec.size / 1024 / 1024).toFixed(2);
        const date = new Date(rec.created * 1000).toLocaleString('de-DE');
        const audioUrl = `${API_BASE.replace('/api', '')}/api/audio/${rec.filename}`;
        const downloadUrl = `${API_BASE.replace('/api', '')}/api/download/${rec.filename}`;
        
        const div = document.createElement('div');
        div.className = 'glass-effect rounded-xl p-4 border border-white/10';
        div.innerHTML = `
            <div class="flex justify-between items-start mb-3">
                <div class="flex-1">
                    <p class="text-white font-semibold text-lg">${rec.filename}</p>
                    <p class="text-gray-400 text-sm mt-1">${sizeMB} MB • ${date}</p>
                </div>
                <button onclick='deleteRecording(${JSON.stringify(rec.filename)})' 
                        class="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg ml-2 transition-all">
                    🗑️ Löschen
                </button>
            </div>
            <div class="flex items-center gap-3">
                <audio controls class="flex-1" preload="metadata">
                    <source src="${audioUrl}" type="audio/flac">
                </audio>
                <a href="${downloadUrl}" download="${rec.filename}" 
                   class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg whitespace-nowrap transition-all">
                    ⬇ Download
                </a>
            </div>
        `;
        list.appendChild(div);
    });
}

function updateSelects() {
    const recordingSelect = document.getElementById('recordingSelect');
    if (!recordingSelect) return;
    
    recordingSelect.innerHTML = '<option value="">-- Auswählen --</option>';
    recordings.forEach(rec => {
        const option = document.createElement('option');
        option.value = rec.filename;
        option.textContent = rec.filename;
        recordingSelect.appendChild(option);
    });
    
    if (recordings.length > 0) {
        const splitSection = document.getElementById('splitSection');
        if (splitSection) {
            splitSection.classList.remove('hidden');
        }
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
        
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 600000);
        
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
            splitBtn.textContent = `✅ ${data.tracks.length} Tracks erstellt`;
            setTimeout(() => {
                splitBtn.textContent = originalText;
            }, 3000);
        } else {
            throw new Error('Keine Tracks erstellt');
        }
        
    } catch (error) {
        if (error.name === 'AbortError') {
            alert('Verarbeitung dauerte zu lange (Timeout nach 10 Minuten).');
        } else {
            alert('Fehler beim Splitting: ' + error.message);
        }
        splitBtn.textContent = originalText;
    } finally {
        splitBtn.disabled = false;
    }
});

function displayTracks(tracks) {
    const list = document.getElementById('tracksList');
    if (!list) return;
    
    list.innerHTML = '';
    
    if (tracks.length === 0) {
        list.innerHTML = '<p class="text-gray-300">Keine Tracks gefunden</p>';
        return;
    }
    
    // Album-Download-Button
    if (tracks.length > 0) {
        const baseFilename = tracks[0].filename.split('_track_')[0];
        const albumDiv = document.createElement('div');
        albumDiv.className = 'glass-effect rounded-xl p-4 mb-4 border border-indigo-500/50';
        albumDiv.innerHTML = `
            <div class="flex justify-between items-center">
                <div>
                    <p class="text-white font-semibold text-lg">📀 Album: ${baseFilename}</p>
                    <p class="text-gray-400 text-sm">${tracks.length} Tracks</p>
                </div>
                <a href="${API_BASE.replace('/api', '')}/api/download-album/${tracks[0].filename}" 
                   class="bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-2 rounded-lg transition-all">
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
        const trackTitle = `Track ${track.track_number}`;
        
        const div = document.createElement('div');
        div.className = 'glass-effect rounded-xl p-4 mb-3 border border-white/10';
        div.innerHTML = `
            <div class="mb-3">
                <p class="text-white font-semibold">Track ${track.track_number}: ${track.filename}</p>
                <p class="text-gray-400 text-sm">Dauer: ${duration}</p>
            </div>
            <div class="flex items-center gap-3">
                <audio controls class="flex-1" preload="metadata">
                    <source src="${audioUrl}" type="audio/flac">
                </audio>
                <a href="${downloadUrl}" download="${track.filename}" 
                   class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg whitespace-nowrap transition-all">
                    ⬇ Download
                </a>
                <button onclick='deleteTrack(${JSON.stringify(track.filename)}, ${JSON.stringify(trackTitle)})' 
                        class="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg transition-all">
                    🗑️ Löschen
                </button>
            </div>
        `;
        list.appendChild(div);
    });
}

// Alben laden
async function loadAlbums() {
    try {
        const response = await fetch(`${API_BASE}/albums`);
        const data = await response.json();
        albums = data.albums || {};
        displayAlbums();
    } catch (error) {
        console.error('Fehler beim Laden der Alben:', error);
    }
}

function displayAlbums() {
    const list = document.getElementById('albumsList');
    if (!list) return;
    
    list.innerHTML = '';
    
    const albumKeys = Object.keys(albums);
    if (albumKeys.length === 0) {
        list.innerHTML = '<p class="text-gray-400 text-center py-12">Keine Alben vorhanden. Starten Sie eine Aufnahme und splitten Sie sie in Tracks.</p>';
        return;
    }
    
    albumKeys.forEach(albumKey => {
        const album = albums[albumKey];
        const coverImg = album.cover ? 
            `<img src="${album.cover}" alt="Cover" class="w-full h-full object-cover rounded-lg">` : 
            '<div class="w-full h-full bg-gradient-to-br from-purple-600 to-indigo-600 rounded-lg flex items-center justify-center text-white text-4xl">🎵</div>';
        
        const div = document.createElement('div');
        div.className = 'glass-effect rounded-xl p-6 border border-white/10';
        div.innerHTML = `
            <div class="flex gap-6">
                <div class="flex-shrink-0 w-32 h-32">
                    ${coverImg}
                </div>
                <div class="flex-1">
                    <h3 class="text-2xl font-bold text-white mb-2">${album.album}</h3>
                    <p class="text-gray-300 text-lg mb-4">${album.artist}</p>
                    ${album.year ? '<p class="text-gray-400 mb-4">Jahr: ' + album.year + '</p>' : ''}
                    <p class="text-gray-400 mb-4">${album.total_tracks} Tracks</p>
                    <div class="flex gap-3">
                        <a href="${API_BASE.replace('/api', '')}/api/download-album/${album.tracks[0].filename}" 
                           class="bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-2 rounded-lg transition-all">
                            ⬇ Album herunterladen
                        </a>
                        <button onclick='deleteAlbum(${JSON.stringify(album.tracks[0].filename)}, ${JSON.stringify(album.album)}, ${JSON.stringify(album.artist)})' 
                                class="bg-red-600 hover:bg-red-700 text-white px-6 py-2 rounded-lg transition-all">
                            🗑️ Album löschen
                        </button>
                    </div>
                </div>
            </div>
            <div class="mt-6 space-y-2">
                ${album.tracks.map(track => {
                    const audioUrl = `${API_BASE.replace('/api', '')}/api/audio/${track.filename}`;
                    const downloadUrl = `${API_BASE.replace('/api', '')}/api/download/${track.filename}`;
                    return `
                        <div class="bg-gray-800/50 rounded-lg p-3 flex items-center gap-3">
                            <span class="text-gray-400 w-8">${track.track_number}</span>
                            <span class="text-white flex-1">${track.title}</span>
                            <audio controls class="flex-1" preload="metadata">
                                <source src="${audioUrl}" type="audio/flac">
                            </audio>
                            <a href="${downloadUrl}" download="${track.filename}" 
                               class="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded-lg text-sm transition-all">
                                ⬇
                            </a>
                            <button onclick='deleteTrack(${JSON.stringify(track.filename)}, ${JSON.stringify(track.title)})' 
                                    class="bg-red-600 hover:bg-red-700 text-white px-3 py-1 rounded-lg text-sm transition-all">
                                🗑️
                            </button>
                        </div>
                    `;
                }).join('')}
            </div>
        `;
        list.appendChild(div);
    });
}

// Gesamte Sammlung herunterladen
document.getElementById('downloadCollectionBtn').addEventListener('click', async () => {
    try {
        window.location.href = `${API_BASE.replace('/api', '')}/api/download-collection`;
    } catch (error) {
        alert('Fehler beim Download: ' + error.message);
    }
});

// Album-Suche
document.getElementById('searchAlbumForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const artist = document.getElementById('searchArtist').value;
    const album = document.getElementById('searchAlbum').value;
    const resultsDiv = document.getElementById('albumSearchResults');
    
    resultsDiv.innerHTML = '<p class="text-white text-center py-4">🔍 Suche...</p>';
    
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
            resultsDiv.innerHTML = '<p class="text-red-400 text-center py-4">Keine Alben gefunden. Versuche andere Suchbegriffe.</p>';
        }
    } catch (error) {
        resultsDiv.innerHTML = `<p class="text-red-400 text-center py-4">Fehler bei der Suche: ${error.message}</p>`;
    }
});

function displayAlbumSearchResults(releases, searchArtist, searchAlbum) {
    const resultsDiv = document.getElementById('albumSearchResults');
    resultsDiv.innerHTML = '';
    
    releases.forEach((release) => {
        const totalTracks = release.total_tracks_all_media || release.track_count || 0;
        const mediaCount = release.media_count || release.media?.length || 0;
        const discCount = release.disc_count || Math.ceil(mediaCount / 2) || 1;
        
        let mediaInfo = '';
        if (release.media && release.media.length > 0) {
            const mediaGroups = [];
            for (let i = 0; i < release.media.length; i += 2) {
                const discNum = Math.floor(i / 2) + 1;
                const sideA = release.media[i];
                const sideB = release.media[i + 1];
                
                if (sideB) {
                    mediaGroups.push(`Platte ${discNum}: Seite ${sideA.position} (${sideA.track_count} Tracks) + Seite ${sideB.position} (${sideB.track_count} Tracks)`);
                } else {
                    mediaGroups.push(`Platte ${discNum}: Seite ${sideA.position} (${sideA.track_count} Tracks)`);
                }
            }
            mediaInfo = mediaGroups.join('<br>');
        } else {
            mediaInfo = `${totalTracks} Tracks gesamt`;
        }
        
        const coverImg = release.cover_url ? 
            `<img src="${release.cover_url}" alt="Cover" class="w-32 h-32 object-cover rounded-lg">` : 
            '<div class="w-32 h-32 bg-gray-700 rounded-lg flex items-center justify-center text-gray-400">Kein Cover</div>';
        
        const discInfo = discCount > 1 ? `<span class="text-yellow-400 font-semibold">${discCount} Platten</span> • ` : '';
        
        const div = document.createElement('div');
        div.className = 'glass-effect rounded-xl p-4 border border-white/10 mb-3';
        div.innerHTML = `
            <div class="flex gap-4">
                <div class="flex-shrink-0">
                    ${coverImg}
                </div>
                <div class="flex-1">
                    <h3 class="text-white font-bold text-lg">${release.title}</h3>
                    <p class="text-gray-300">${release.artist}</p>
                    <p class="text-gray-400 text-sm mt-2">
                        ${release.date ? 'Jahr: ' + release.date + ' • ' : ''}
                        ${discInfo}${totalTracks} Tracks gesamt (${mediaCount} Seiten)<br>
                        <span class="text-gray-500 text-xs mt-1 block">${mediaInfo}</span>
                    </p>
                    <button onclick='selectAlbum("${release.mbid}", ${JSON.stringify(release.title)}, ${totalTracks})' 
                            class="mt-3 bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg transition-all">
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
            loadAlbums();
        } else {
            alert('Fehler: ' + data.error);
        }
    } catch (error) {
        alert('Fehler beim Tagging: ' + error.message);
    }
}

// Aufnahme löschen
async function deleteRecording(filename) {
    if (!confirmAction(`Möchten Sie "${filename}" wirklich löschen?`)) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/delete/${filename}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            loadRecordings();
            loadAlbums();
        } else {
            const data = await response.json().catch(() => ({}));
            alert('Fehler beim Löschen: ' + (data.error || 'Unbekannter Fehler'));
        }
    } catch (error) {
        alert('Fehler: ' + error.message);
    }
}

// Track löschen
async function deleteTrack(filename, trackTitle) {
    if (!confirmAction(`Möchten Sie "${trackTitle}" (${filename}) wirklich löschen?`)) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/delete/${filename}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            alert('✅ Track erfolgreich gelöscht');
            loadRecordings();
            loadAlbums();
        } else {
            const data = await response.json().catch(() => ({}));
            alert('Fehler beim Löschen: ' + (data.error || 'Unbekannter Fehler'));
        }
    } catch (error) {
        alert('Fehler: ' + error.message);
    }
}

// Album löschen
async function deleteAlbum(baseFilename, albumTitle, artist) {
    const albumName = `${artist} - ${albumTitle}`;
    if (!confirmAction(`Möchten Sie das komplette Album "${albumName}" wirklich löschen?\n\nDies löscht alle Tracks, das Cover und die Original-Aufnahme.`)) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/delete-album/${baseFilename}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (response.ok) {
            alert(`✅ Album erfolgreich gelöscht\n\n${data.count} Dateien wurden entfernt.`);
            loadRecordings();
            loadAlbums();
        } else {
            alert('Fehler beim Löschen: ' + (data.error || 'Unbekannter Fehler'));
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
        
        const statusResponse = await fetch(`${API_BASE}/status`);
        const status = await statusResponse.json();
        
        // PyAudio-Geräte
        const deviceSelect = document.getElementById('audioDeviceSelect');
        if (deviceSelect) {
            deviceSelect.innerHTML = '<option value="-1">Standard-Gerät</option>';
            if (status.devices) {
                status.devices.forEach(device => {
                    const option = document.createElement('option');
                    option.value = device.index;
                    option.textContent = `${device.index}: ${device.name} (${device.channels} Kanäle)`;
                    if (device.index === status.current_device) {
                        option.selected = true;
                    }
                    deviceSelect.appendChild(option);
                });
            }
        }
        
        // ALSA-Geräte
        const alsaSelect = document.getElementById('alsaDeviceSelect');
        if (alsaSelect) {
            alsaSelect.innerHTML = '<option value="">-- Auswählen --</option>';
            if (status.alsa_devices && status.alsa_devices.length > 0) {
                status.alsa_devices.forEach(device => {
                    const option = document.createElement('option');
                    option.value = device.alsa_id;
                    option.textContent = `${device.name} (${device.alsa_id})`;
                    if (status.current_device === device.alsa_id) {
                        option.selected = true;
                    }
                    alsaSelect.appendChild(option);
                });
            }
        }
        
        // Audio-Einstellungen
        if (settings.audio) {
            document.getElementById('sampleRateSelect').value = settings.audio.sample_rate || 44100;
            document.getElementById('channelsSelect').value = settings.audio.channels || 2;
            if (settings.audio.alsa_device && alsaSelect) {
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
            const autoStopInput = document.getElementById('autoStopSilence');
            if (autoStopInput) {
                const autoStopValue = settings.recording.auto_stop_silence_duration;
                autoStopInput.value = autoStopValue !== undefined && autoStopValue !== null ? autoStopValue : 10.0;
            }
        }
    } catch (error) {
        console.error('Fehler beim Laden der Einstellungen:', error);
    }
}

// Einstellungen speichern
document.getElementById('settingsForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const formData = new FormData(e.target);
    const useTimestamp = document.getElementById('useTimestamp').checked;
    
    const settingsData = new FormData();
    settingsData.append('audio_device_index', parseInt(formData.get('audio_device_index')));
    
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
    const autoStopRaw = formData.get('recording_auto_stop_silence_duration');
    if (autoStopRaw !== null) {
        settingsData.append('recording_auto_stop_silence_duration', parseFloat(autoStopRaw));
    }
    
    try {
        const response = await fetch(`${API_BASE}/settings`, {
            method: 'POST',
            body: settingsData
        });
        
        const data = await response.json();
        
        if (response.ok) {
            alert('✅ Einstellungen erfolgreich gespeichert!');
            loadSettings();
        } else {
            alert('Fehler: ' + data.error);
        }
    } catch (error) {
        alert('Fehler beim Speichern: ' + error.message);
    }
});

// Initialisierung
initTabs();
initWaveform();
connectWebSocket();
loadRecordings();
loadSettings();

// Prüfe sofort den Status beim Laden
checkRecordingStatus();

// Prüfe regelmäßig den Aufnahme-Status (alle 2 Sekunden)
statusCheckInterval = setInterval(checkRecordingStatus, 2000);

// Aktualisiere Aufnahmen-Liste regelmäßig
setInterval(() => {
    loadRecordings();
    if (!document.getElementById('contentAlbums').classList.contains('hidden')) {
        loadAlbums();
    }
}, 10000); // Alle 10 Sekunden aktualisieren

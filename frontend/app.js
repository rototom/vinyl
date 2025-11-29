const API_BASE = 'http://localhost:8000/api';
let ws = null;
let recordings = [];

// WebSocket für Audio-Level
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.hostname;
    const port = window.location.port || '8000';
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
        
        const div = document.createElement('div');
        div.className = 'bg-gray-800 rounded-lg p-4 flex justify-between items-center';
        div.innerHTML = `
            <div>
                <p class="text-white font-semibold">${rec.filename}</p>
                <p class="text-gray-400 text-sm">${sizeMB} MB • ${date}</p>
            </div>
            <button onclick="deleteRecording('${rec.filename}')" 
                    class="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg">
                Löschen
            </button>
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
    
    try {
        const formData = new FormData();
        formData.append('filename', filename);
        
        document.getElementById('splitBtn').disabled = true;
        document.getElementById('splitBtn').textContent = '⏳ Verarbeitung...';
        
        const response = await fetch(`${API_BASE}/split-tracks`, {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (response.ok) {
            displayTracks(data.tracks);
            updateTrackSelect(data.tracks);
            document.getElementById('tagSection').classList.remove('hidden');
            document.getElementById('splitBtn').textContent = '🔪 Tracks automatisch splitten';
        } else {
            alert('Fehler: ' + data.error);
            document.getElementById('splitBtn').textContent = '🔪 Tracks automatisch splitten';
        }
        document.getElementById('splitBtn').disabled = false;
    } catch (error) {
        alert('Fehler beim Splitting: ' + error.message);
        document.getElementById('splitBtn').disabled = false;
        document.getElementById('splitBtn').textContent = '🔪 Tracks automatisch splitten';
    }
});

function displayTracks(tracks) {
    const list = document.getElementById('tracksList');
    list.innerHTML = '';
    
    tracks.forEach(track => {
        const duration = formatTime(track.duration);
        const div = document.createElement('div');
        div.className = 'bg-gray-800 rounded-lg p-4';
        div.innerHTML = `
            <p class="text-white font-semibold">Track ${track.track_number}: ${track.filename}</p>
            <p class="text-gray-400 text-sm">Dauer: ${duration}</p>
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

// Initialisierung
connectWebSocket();
loadRecordings();
setInterval(loadRecordings, 5000); // Alle 5 Sekunden aktualisieren


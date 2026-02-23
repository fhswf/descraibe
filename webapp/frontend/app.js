/* app.js – Audiodeskription Pipeline Wizard */
'use strict';

// ── State ──────────────────────────────────────────────────────────────────────
const STATE = {
    jobId: null,
    currentStep: 0,
    doneSteps: new Set(),
    sse: null,
    gptRecords: [],
};

// ── Initialization ─────────────────────────────────────────────────────────────
async function checkSystemInfo() {
    try {
        const res = await fetch('/api/system_info');
        const data = await res.json();
        const badge = document.getElementById('gpu-status-badge');
        if (badge) {
            if (data.gpu_available) {
                badge.textContent = 'GPU-Status: 🟢 Aktiv';
                badge.style.color = '#fff';
            } else {
                badge.textContent = 'GPU-Status: 🔴 Nicht verfügbar (CPU-Modus)';
                badge.style.color = 'var(--accent)';
            }
        }
    } catch (e) {
        console.warn('Could not fetch system info:', e);
    }
}
window.addEventListener('DOMContentLoaded', checkSystemInfo);

// ── Navigation ─────────────────────────────────────────────────────────────────
function goTo(step) {
    document.querySelectorAll('.step-panel').forEach((p, i) => {
        p.classList.toggle('visible', i === step);
    });
    document.querySelectorAll('.step-btn').forEach((b, i) => {
        b.classList.toggle('active', i === step);
        if (STATE.doneSteps.has(i)) b.classList.add('done');
        else b.classList.remove('done');
    });
    STATE.currentStep = step;

    // Refresh GPT config preview on step 6
    if (step === 6) renderGptConfigPreview();
    if (step === 7) renderResults();
}

function markDone(step) {
    STATE.doneSteps.add(step);
    const btn = document.querySelectorAll('.step-btn')[step];
    if (btn) btn.classList.add('done');
}

// ── SSE connection ──────────────────────────────────────────────────────────────
function connectSSE(jobId) {
    if (STATE.sse) STATE.sse.close();
    STATE.sse = new EventSource(`/api/status/${jobId}`);
    STATE.sse.onmessage = (ev) => {
        try {
            const payload = JSON.parse(ev.data);
            handleSSEEvent(payload);
        } catch (e) { /* ignore */ }
    };
    STATE.sse.onerror = () => STATE.sse.close();
}

function handleSSEEvent(payload) {
    const { event, data } = payload;
    if (!event) return;

    if (event === 'progress') {
        handleProgress(data);
    } else if (event === 'vad_done') {
        onVADDone(data);
    } else if (event === 'transcribe_done') {
        onTranscribeDone(data);
    } else if (event === 'slots_done') {
        onSlotsDone(data);
    } else if (event === 'images_done') {
        onImagesDone(data);
    } else if (event === 'gpt_done') {
        onGPTDone(data);
    } else if (event === 'error') {
        showError(data.step, data.message);
    }
}

function handleProgress(data) {
    const step = data.step;
    const msg = data.message || '';
    const cur = data.current ?? null;
    const total = data.total ?? null;

    if (step === 'vad') {
        document.getElementById('vad-msg').textContent = msg;
        animateBar('vad-bar', cur, total);
    } else if (step === 'transcribe') {
        document.getElementById('transcribe-msg').textContent = msg;
        animateBar('transcribe-bar', cur, total);
    } else if (step === 'slots') {
        document.getElementById('slots-msg').textContent = msg;
        animateBar('slots-bar', cur, total);
    } else if (step === 'images') {
        document.getElementById('images-msg').textContent = msg;
        animateBar('images-bar', cur, total);
    } else if (step === 'gpt') {
        document.getElementById('gpt-progress-msg').textContent = msg;
        animateBar('gpt-bar', cur, total);
        appendFeedLine(msg, 'info');
    }
}

function animateBar(id, cur, total) {
    const el = document.getElementById(id);
    if (!el) return;
    if (cur !== null && total !== null && total > 0) {
        el.style.width = Math.max(1, Math.round((cur / total) * 100)) + '%';
        el.classList.remove('indeterminate-pulse');
    } else {
        // indeterminate – pulse at 60%
        if (parseFloat(el.style.width || '0') < 60) el.style.width = '60%';
        el.classList.add('indeterminate-pulse');
    }
}

// ── Step 0: Upload ──────────────────────────────────────────────────────────────
(function initUpload() {
    const dz = document.getElementById('drop-zone');
    dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('drag-over'); });
    dz.addEventListener('dragleave', () => dz.classList.remove('drag-over'));
    dz.addEventListener('drop', e => {
        e.preventDefault();
        dz.classList.remove('drag-over');
        const file = e.dataTransfer.files[0];
        if (file) doUpload(file);
    });

    document.getElementById('video-file-input').addEventListener('change', e => {
        if (e.target.files[0]) doUpload(e.target.files[0]);
    });
})();

function resetSession() {
    STATE.jobId = null;
    STATE.currentStep = 0;
    STATE.doneSteps.clear();
    STATE.gptRecords = [];
    if (STATE.sse) STATE.sse.close();
    STATE.sse = null;

    // Remove active/done from all sidebar buttons
    document.querySelectorAll('.step-btn').forEach(b => b.classList.remove('done', 'active'));

    // Hide all result cards
    document.querySelectorAll('.card').forEach(c => {
        if (c.id.endsWith('-results-card') || c.id.endsWith('-quality-card') || c.id === 'video-stats-card' || c.id === 'gpt-done-card' || c.id === 'results-records-card') {
            c.style.display = 'none';
        }
    });

    // Reset progress bars
    document.querySelectorAll('.progress-bar-fill').forEach(el => el.style.width = '0%');
}

// Chunk size for upload (e.g., 5MB)
const CHUNK_SIZE = 5 * 1024 * 1024;

async function doUpload(file) {
    resetSession();

    const prog = document.getElementById('upload-progress');
    const bar = document.getElementById('upload-bar');
    const msg = document.getElementById('upload-msg');
    prog.classList.add('visible');
    bar.style.width = '0%';
    msg.textContent = 'Bereite Upload vor...';

    const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
    let jobId = localStorage.getItem('ad_job_id');
    let startingChunk = 0;

    try {
        // 1. Initialize or check status
        if (jobId) {
            msg.textContent = 'Prüfe auf abgebrochenen Upload...';
            const statusRes = await fetch(`/api/upload_status?job_id=${jobId}&filename=${encodeURIComponent(file.name)}`);
            if (statusRes.ok) {
                const statusData = await statusRes.json();
                if (statusData.uploaded_bytes) {
                    startingChunk = Math.floor(statusData.uploaded_bytes / CHUNK_SIZE);
                    console.log(`Resuming from chunk ${startingChunk} / ${totalChunks}`);
                }
            } else {
                jobId = null; // Job doesn't exist anymore on server
            }
        }

        // 2. Initialize job if we don't have one (or it was invalid)
        if (!jobId || startingChunk === 0) {
            msg.textContent = 'Starte Upload...';
            const initFormData = new FormData();
            initFormData.append('filename', file.name);
            initFormData.append('total_size', file.size);
            if (jobId) initFormData.append('job_id', jobId);

            const initRes = await fetch('/api/upload', { method: 'POST', body: initFormData });
            if (!initRes.ok) throw new Error('Initialisierung fehlgeschlagen');
            const initData = await initRes.json();

            if (initData.error) throw new Error(initData.error);
            jobId = initData.job_id;
            localStorage.setItem('ad_job_id', jobId);
            startingChunk = 0;
        }

        STATE.jobId = jobId;
        document.getElementById('job-badge').textContent = 'Job: ' + STATE.jobId.slice(0, 8) + '…';

        // 3. Upload chunks sequentially
        for (let i = startingChunk; i < totalChunks; i++) {
            const start = i * CHUNK_SIZE;
            const end = Math.min(start + CHUNK_SIZE, file.size);
            const chunk = file.slice(start, end);

            const fd = new FormData();
            fd.append('job_id', STATE.jobId);
            fd.append('filename', file.name);
            fd.append('chunkIndex', i);
            fd.append('totalChunks', totalChunks);
            fd.append('chunk', chunk, file.name);

            msg.textContent = `Lade Teil ${i + 1} von ${totalChunks} hoch...`;

            let retryCount = 0;
            let success = false;
            let finalData = null;

            while (!success && retryCount < 3) {
                try {
                    const chunkRes = await fetch('/api/upload_chunk', { method: 'POST', body: fd });
                    if (!chunkRes.ok) throw new Error(`HTTP error! status: ${chunkRes.status}`);

                    const data = await chunkRes.json();
                    if (data.error) throw new Error(data.error);

                    success = true;
                    if (data.complete) {
                        finalData = data;
                    }
                } catch (err) {
                    retryCount++;
                    console.error(`Chunk ${i} failed (attempt ${retryCount}/3):`, err);
                    if (retryCount >= 3) {
                        throw new Error('Upload nach mehreren Versuchen abgebrochen.');
                    }
                    // Wait slightly before retry
                    await new Promise(r => setTimeout(r, 1000 * retryCount));
                }
            }

            // Update Progress Bar
            const progress = ((i + 1) / totalChunks) * 100;
            bar.style.width = Math.round(progress) + '%';

            // If complete, finish up
            if (finalData && finalData.complete) {
                bar.style.width = '100%';
                msg.textContent = '✅ Upload abgeschlossen';

                renderVideoStats(finalData.stats);
                markDone(0);
                goTo(1); // Jump to VAD step visually
                connectSSE(STATE.jobId);
                return; // Done
            }
        }

    } catch (err) {
        msg.textContent = '❌ ' + err.message;
        msg.innerHTML += '<br><button class="btn btn-primary" onclick="doUpload(document.getElementById(\'video-file-input\').files[0])" style="margin-top: 10px;">Upload fortsetzen / wiederholen</button>';
    }
}

function renderVideoStats(stats) {
    const card = document.getElementById('video-stats-card');
    const grid = document.getElementById('video-stats-grid');
    card.style.display = 'block';

    const fields = [
        ['Dateiname', stats.filename],
        ['Dauer', formatDuration(stats.duration_s)],
        ['FPS', stats.fps],
        ['Auflösung', `${stats.width} × ${stats.height}`],
        ['Frames', stats.frame_count?.toLocaleString()],
        ['Größe', formatBytes(stats.size_bytes)],
    ];

    grid.innerHTML = fields.map(([label, val]) => `
    <div class="stat-card">
      <span class="stat-label">${label}</span>
      <span class="stat-value">${val}</span>
    </div>
  `).join('');
}

// ── Step 1: VAD ─────────────────────────────────────────────────────────────────
function runVAD() {
    if (!STATE.jobId) return alert('Bitte zuerst ein Video hochladen.');
    document.getElementById('vad-progress-card').style.display = 'block';
    document.getElementById('vad-results-card').style.display = 'none';

    fetch('/api/run/vad', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            job_id: STATE.jobId,
            threshold: parseFloat(document.getElementById('vad-threshold').value),
            min_speech_duration_ms: parseInt(document.getElementById('vad-min-speech').value),
            min_silence_duration_ms: parseInt(document.getElementById('vad-min-silence').value),
            min_pause_duration_s: parseFloat(document.getElementById('vad-min-pause').value),
        }),
    });
}

function onVADDone(data) {
    document.getElementById('vad-progress-card').style.display = 'none';
    const card = document.getElementById('vad-results-card');
    card.style.display = 'block';
    document.getElementById('vad-table').innerHTML = buildTable(data.pauses, ['slot', 'start_s', 'end_s', 'dur_s']);
    markDone(1);
}

// ── Step 2: Transcription ───────────────────────────────────────────────────────
function runTranscribe() {
    if (!STATE.jobId) return alert('Bitte zuerst ein Video hochladen.');
    document.getElementById('transcribe-progress-card').style.display = 'block';
    document.getElementById('transcribe-results-card').style.display = 'none';

    fetch('/api/run/transcribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            job_id: STATE.jobId,
            model_size: document.getElementById('whisper-model').value,
            language: document.getElementById('whisper-lang').value,
            use_fw_vad: document.getElementById('whisper-vad').value === 'true',
        }),
    });
}

function uploadSRT(input) {
    if (!STATE.jobId) return alert('Bitte zuerst ein Video hochladen.');
    const file = input.files[0];
    if (!file) return;

    const fd = new FormData();
    fd.append('job_id', STATE.jobId);
    fd.append('srt', file);

    document.getElementById('srt-upload-status').textContent = 'Wird hochgeladen…';

    fetch('/api/upload_srt', { method: 'POST', body: fd }).then(r => r.json()).then(data => {
        if (data.error) {
            document.getElementById('srt-upload-status').textContent = '❌ ' + data.error;
            return;
        }
        document.getElementById('srt-upload-status').textContent = `✅ ${data.segment_count} Segmente geladen`;
        onTranscribeDone(data);
        markDone(2);
    });
}

function onTranscribeDone(data) {
    document.getElementById('transcribe-progress-card').style.display = 'none';
    const card = document.getElementById('transcribe-results-card');
    card.style.display = 'block';

    const meta = data.metadata || {};
    document.getElementById('transcribe-meta').innerHTML = `
    <div style="display:flex;gap:8px;flex-wrap:wrap;">
      ${meta.language ? `<span class="badge badge-teal">Sprache: ${meta.language} (${(meta.language_prob * 100).toFixed(0)}%)</span>` : ''}
      ${meta.segment_count != null ? `<span class="badge badge-violet">${meta.segment_count} Segmente</span>` : ''}
      ${data.segment_count != null ? `<span class="badge badge-violet">${data.segment_count} Segmente</span>` : ''}
    </div>`;

    const rows = data.segments || [];
    document.getElementById('transcribe-table').innerHTML = buildTable(
        rows.slice(0, 200),
        ['start_s', 'end_s', 'text', 'avg_logprob', 'no_speech_prob']
    );
    markDone(2);
}

// ── Step 3: Slots ───────────────────────────────────────────────────────────────
function runSlots() {
    if (!STATE.jobId) return alert('Bitte zuerst Sprechpausen erkennen.');
    document.getElementById('slots-progress-card').style.display = 'block';
    document.getElementById('slots-quality-card').style.display = 'none';

    fetch('/api/run/slots', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            job_id: STATE.jobId,
            min_slot_s: parseFloat(document.getElementById('slot-min-s').value),
            pad_in_s: parseFloat(document.getElementById('slot-pad-in').value),
            pad_out_s: parseFloat(document.getElementById('slot-pad-out').value),
            filter_whisper: document.getElementById('slot-filter-whisper').value === 'true',
        }),
    });
}

function onSlotsDone(data) {
    document.getElementById('slots-progress-card').style.display = 'none';
    const card = document.getElementById('slots-quality-card');
    card.style.display = 'block';

    const q = data.quality || {};
    document.getElementById('slots-quality-summary').innerHTML = `
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;">
        <span class="badge badge-violet">${data.slot_count} Slots</span>
        <span class="badge badge-green">🟢 ${q.green_count} OK</span>
        <span class="badge badge-yellow">🟡 ${q.yellow_count} Grenzwertig</span>
        <span class="badge badge-red">🔴 ${q.red_count} Kritisch</span>
      </div>`;

    const painted = (data.slots || []).map(r => ({ ...r, _color: '' }));
    document.getElementById('slots-table').innerHTML = buildTable(
        painted, ['slot', 'start_s', 'end_s', 'dur_s']
    );
    markDone(3);
}

// ── Step 4: Images ──────────────────────────────────────────────────────────────
function runImages() {
    if (!STATE.jobId) return alert('Bitte zuerst AD-Slots generieren.');
    document.getElementById('images-progress-card').style.display = 'block';
    document.getElementById('images-results-card').style.display = 'none';

    fetch('/api/run/images', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            job_id: STATE.jobId,
            threshold: parseFloat(document.getElementById('img-threshold').value),
            blur_threshold: parseFloat(document.getElementById('img-blur').value),
            min_scene_length: parseInt(document.getElementById('img-min-scene').value),
            short_scene_s: parseFloat(document.getElementById('img-short-scene').value),
        }),
    });
}

function onImagesDone(data) {
    document.getElementById('images-progress-card').style.display = 'none';
    const card = document.getElementById('images-results-card');
    card.style.display = 'block';

    document.getElementById('images-summary').innerHTML = `
    <div style="display:flex;gap:8px;flex-wrap:wrap;">
      <span class="badge badge-violet">${data.scene_count} Szenenbilder</span>
      <span class="badge badge-teal">${data.slots_mapped} Slots gemappt</span>
    </div>`;

    // Show first few images from slot_map
    const gallery = document.getElementById('images-gallery');
    const slotMap = data.slot_map || [];
    const imgs = slotMap.filter(r => r.image_path).slice(0, 20);
    gallery.innerHTML = imgs.map(r => {
        const name = r.image_path.split('/').pop();
        return `<img class="gallery-img" src="/api/preview/${STATE.jobId}/image/${name}"
      alt="Slot ${r.slot}" title="Slot ${r.slot}: ${r.start_s}s–${r.end_s}s"
      onerror="this.style.display='none'" />`;
    }).join('');

    markDone(4);
}

// ── Step 5: Prompts (no async, just navigation) ─────────────────────────────────
function renderGptConfigPreview() {
    const el = document.getElementById('gpt-config-summary');
    el.innerHTML = `
    <div style="display:flex;gap:8px;flex-wrap:wrap;">
      <span class="badge badge-violet">Modell: ${v('gpt-model')}</span>
      <span class="badge badge-teal">T=${v('gpt-temp')}</span>
      <span class="badge badge-teal">MaxTok=${v('gpt-max-tokens')}</span>
      <span class="badge badge-violet">Cut: ${v('gpt-cut')}</span>
      <span class="badge badge-violet">Detail: ${v('gpt-detail')}</span>
      ${v('system-prompt') ? '<span class="badge badge-green">System ✅</span>' : '<span class="badge badge-red">System fehlt!</span>'}
      ${v('user-prompt') ? '<span class="badge badge-green">User ✅</span>' : '<span class="badge badge-red">User fehlt!</span>'}
      ${v('api-key') ? '<span class="badge badge-green">API Key ✅</span>' : '<span class="badge badge-red">API Key fehlt!</span>'}
    </div>`;
}

// ── Step 6: GPT Generation ──────────────────────────────────────────────────────
function runGPT() {
    const apiKey = v('api-key');
    if (!apiKey) return alert('Bitte OpenAI API Key eingeben.');
    if (!v('system-prompt') || !v('user-prompt')) return alert('System- und User-Instruktion sind Pflichtfelder.');
    if (!STATE.jobId) return alert('Bitte zuerst alle vorherigen Schritte abschließen.');

    document.getElementById('gpt-progress-card').style.display = 'block';
    document.getElementById('gpt-done-card').style.display = 'none';
    document.getElementById('gpt-bar').style.width = '0%';
    document.getElementById('gpt-feed').innerHTML = '';

    // Combine prompts
    const adRules = v('ad-rules');
    const fewShots = v('few-shots');
    let systemFinal = v('system-prompt');
    if (adRules) systemFinal += '\n\n# AD-Regeln\n' + adRules;
    if (fewShots) systemFinal += '\n\n# Few-Shots\n' + fewShots;

    fetch('/api/run/gpt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            job_id: STATE.jobId,
            api_key: apiKey,
            system_prompt: systemFinal,
            user_prompt: v('user-prompt'),
            model: v('gpt-model'),
            temperature: parseFloat(v('gpt-temp')),
            max_tokens: parseInt(v('gpt-max-tokens')),
            detail: v('gpt-detail'),
            cut: v('gpt-cut'),
        }),
    });
}

function onGPTDone(data) {
    document.getElementById('gpt-bar').style.width = '100%';
    document.getElementById('gpt-done-card').style.display = 'block';

    const okCount = data.ok_count ?? 0;
    const skipCount = data.skip_count ?? 0;
    const errCount = data.error_count ?? 0;

    document.getElementById('gpt-done-summary').innerHTML = `
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;">
      <span class="badge badge-green">✅ ${okCount} generiert</span>
      <span class="badge badge-yellow">⏩ ${skipCount} übersprungen</span>
      ${errCount ? `<span class="badge badge-red">❌ ${errCount} Fehler</span>` : ''}
    </div>
    <p style="font-size:0.875rem;color:var(--text-secondary)">Ausgabedateien stehen im nächsten Schritt zum Download bereit.</p>`;

    STATE.gptRecords = data.records || [];
    markDone(6);
    appendFeedLine(`✅ Fertig – ${okCount} Beschreibungen generiert`, 'ok');
}

function appendFeedLine(msg, cls = 'info') {
    const feed = document.getElementById('gpt-feed');
    const line = document.createElement('div');
    line.className = 'feed-line ' + cls;
    line.textContent = msg;
    feed.appendChild(line);
    feed.scrollTop = feed.scrollHeight;
}

// ── Step 7: Results ─────────────────────────────────────────────────────────────
function renderResults() {
    if (!STATE.jobId) return;

    fetch(`/api/results/${STATE.jobId}`).then(r => r.json()).then(data => {
        const paths = data.output_paths || {};
        const list = document.getElementById('download-list');

        const fileLabels = {
            gesamt_txt: { icon: '📄', name: 'AD-Gesamtdatei', type: 'TXT' },
            quality_txt: { icon: '📋', name: 'Qualitätsdatei', type: 'TXT' },
            frazier_csv: { icon: '📊', name: 'Frazier-Format', type: 'CSV' },
            directors_tsv: { icon: '🎬', name: "Director's Cut", type: 'TSV' },
        };

        list.innerHTML = Object.entries(paths).map(([key, name]) => {
            const info = fileLabels[key] || { icon: '📁', name: key, type: '' };
            return `<a class="download-item" href="/api/download/${STATE.jobId}/${key}" download>
        <span class="download-icon">${info.icon}</span>
        <span class="download-name">${info.name}</span>
        <span class="download-type">${name} &nbsp; ${info.type}</span>
        <span>↓</span>
      </a>`;
        }).join('');

        if (list.innerHTML === '') {
            list.innerHTML = '<div class="alert alert-warn">⚠️ Noch keine Dateien verfügbar. Bitte GPT-Schritt abschließen.</div>';
        }
    });

    // Show generated texts
    if (STATE.gptRecords.length > 0) {
        document.getElementById('results-records-card').style.display = 'block';
        const cols = ['slot', 'start_s', 'end_s', 'duration_s', 'text'];
        document.getElementById('results-table').innerHTML = buildTable(STATE.gptRecords, cols);
        markDone(7);
    }
}

// ── Error display ───────────────────────────────────────────────────────────────
function showError(step, message) {
    console.error(`[${step}] ${message}`);
    const alertHtml = `<div class="alert alert-error" style="margin-top:12px;">❌ ${escHtml(message)}</div>`;

    const map = {
        vad: 'vad-progress-card',
        transcribe: 'transcribe-progress-card',
        slots: 'slots-progress-card',
        images: 'images-progress-card',
        gpt: 'gpt-progress-card',
    };
    const el = map[step] ? document.getElementById(map[step]) : null;
    if (el) el.insertAdjacentHTML('afterend', alertHtml);
}

// ── Utilities ───────────────────────────────────────────────────────────────────
function v(id) {
    return (document.getElementById(id)?.value || '').trim();
}

function escHtml(str) {
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function formatDuration(s) {
    if (!s) return '—';
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = Math.round(s % 60);
    if (h > 0) return `${h}h ${m}m ${sec}s`;
    if (m > 0) return `${m}m ${sec}s`;
    return `${sec}s`;
}

function formatBytes(b) {
    if (!b) return '—';
    if (b > 1e9) return (b / 1e9).toFixed(1) + ' GB';
    if (b > 1e6) return (b / 1e6).toFixed(1) + ' MB';
    return (b / 1e3).toFixed(1) + ' KB';
}

function buildTable(rows, cols) {
    if (!rows || rows.length === 0) return '<p style="padding:12px;color:var(--text-muted)">Keine Daten</p>';
    const head = cols.map(c => `<th>${escHtml(c)}</th>`).join('');
    const body = rows.map(row => {
        const cells = cols.map(c => {
            const val = row[c] ?? '';
            const display = typeof val === 'number' ? String(val) : String(val).slice(0, 120);
            return `<td>${escHtml(display)}</td>`;
        }).join('');
        return `<tr>${cells}</tr>`;
    }).join('');
    return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

// ── Session Restoration ────────────────────────────────────────────────────────
function restoreSession() {
    const savedJobId = localStorage.getItem('ad_job_id');
    if (!savedJobId) return;

    fetch(`/api/results/${savedJobId}`)
        .then(r => r.ok ? r.json() : Promise.reject('Not found'))
        .then(data => {
            if (data.error) throw new Error(data.error);

            STATE.jobId = data.job_id;
            document.getElementById('job-badge').textContent = 'Job: ' + STATE.jobId.slice(0, 8) + '…';

            // Reconstruct timeline visually
            if (data.video_stats) {
                renderVideoStats(data.video_stats);
                markDone(0);
                document.getElementById('upload-bar').style.width = '100%';
                document.getElementById('upload-msg').textContent = '✅ Session wiederhergestellt';
                document.getElementById('upload-progress').classList.add('visible');
            }

            let nextStep = 1;

            if (data.pauses_count > 0) {
                markDone(1);
                document.getElementById('vad-results-card').style.display = 'block';
                document.getElementById('vad-table').innerHTML = `<p style="padding:12px;color:var(--text-muted)">${data.pauses_count} Sprechpausen geladen.</p>`;
                nextStep = 2;
            }

            if (data.transcript_meta) {
                markDone(2);
                document.getElementById('transcribe-results-card').style.display = 'block';
                document.getElementById('transcribe-meta').innerHTML = `<span class="badge badge-green">Transkript geladen</span>`;
                nextStep = 3;
            }

            if (data.slots_count > 0) {
                markDone(3);
                document.getElementById('slots-quality-card').style.display = 'block';
                if (data.quality_report) {
                    const q = data.quality_report;
                    document.getElementById('slots-quality-summary').innerHTML = `
                      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;">
                        <span class="badge badge-violet">${data.slots_count} Slots</span>
                        <span class="badge badge-green">🟢 ${q.green_count} OK</span>
                        <span class="badge badge-yellow">🟡 ${q.yellow_count} Grenzwertig</span>
                        <span class="badge badge-red">🔴 ${q.red_count} Kritisch</span>
                      </div>
                    `;
                }
                nextStep = 4;
            }

            if (data.images_count > 0) {
                markDone(4);
                document.getElementById('images-results-card').style.display = 'block';
                document.getElementById('images-summary').innerHTML = `<span class="badge badge-violet">${data.images_count} Bilder geladen</span>`;
                nextStep = 5;
            }

            if (data.output_paths && Object.keys(data.output_paths).length > 0) {
                markDone(6);
                document.getElementById('gpt-done-card').style.display = 'block';
                document.getElementById('gpt-done-summary').innerHTML = `<span class="badge badge-green">✅ Skripte generiert</span>`;
                nextStep = 7;
            }

            connectSSE(STATE.jobId);
            goTo(nextStep);
        })
        .catch(err => {
            console.warn("Could not restore session:", err);
            localStorage.removeItem('ad_job_id');
        });
}

document.addEventListener('DOMContentLoaded', () => {
    restoreSession();
});

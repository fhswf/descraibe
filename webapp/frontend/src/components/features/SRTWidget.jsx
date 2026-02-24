import React, { useState, useEffect } from 'react';
import { useJob } from '../../hooks/useJob.jsx';

export function SRTWidget() {
    const { jobId, jobData, setFocusedSlot } = useJob();
    const [texts, setTexts] = useState({});
    const [saving, setSaving] = useState(false);

    // Determines if we should show hours based on the total video length
    // We can infer max duration from the last GPT record's end_s
    const maxDuration = jobData?.gpt_records?.length > 0
        ? Math.max(...jobData.gpt_records.map(rec => rec.end_s || 0))
        : 0;

    const formatTime = (seconds) => {
        if (!seconds || isNaN(seconds)) seconds = 0;
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = seconds % 60;
        const mm = m.toString().padStart(2, '0');
        const ss = s.toFixed(2).padStart(5, '0');

        if (maxDuration < 3600) {
            return `${mm}:${ss}`;
        }

        const hh = h.toString().padStart(2, '0');
        return `${hh}:${mm}:${ss}`;
    };

    useEffect(() => {
        if (jobData?.gpt_records) {
            const initialTexts = {};
            jobData.gpt_records.forEach(rec => {
                initialTexts[rec.slot] = rec.text || '';
            });
            setTexts(initialTexts);
        }
    }, [jobData?.gpt_records]);

    if (!jobData?.gpt_records || jobData.gpt_records.length === 0) {
        return null; // Only show when there are records
    }

    const handleChange = (slotId, newText) => {
        setTexts(prev => ({ ...prev, [slotId]: newText }));
    };

    const handleSave = async () => {
        setSaving(true);
        try {
            const res = await fetch(`/api/jobs/${jobId}/texts`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ texts })
            });
            if (!res.ok) {
                const data = await res.json();
                throw new Error(data.error || 'Failed to save texts');
            }
            alert("Änderungen erfolgreich gespeichert! Die Ausgabedateien wurden aktualisiert.");
        } catch (err) {
            alert("Error: " + err.message);
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="srt-widget" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px', flexShrink: 0 }}>
                <p className="card-title" style={{ margin: 0 }}>AD-Texte bearbeiten (SRT Ansicht)</p>
                <button
                    className="btn btn-primary"
                    onClick={handleSave}
                    disabled={saving}
                >
                    {saving ? 'Speichert...' : '💾 Änderungen speichern'}
                </button>
            </div>

            <div className="srt-list" style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '10px', minHeight: 0 }}>
                {jobData.gpt_records.map((rec, idx) => (
                    <div key={idx} style={{ padding: '10px', backgroundColor: '#f8f9fa', border: '1px solid #dee2e6', borderRadius: '4px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '0.9rem', color: '#6c757d' }}>
                            <strong>Slot {rec.slot}</strong>
                            <span style={{ fontFamily: 'monospace' }}>
                                {formatTime(rec.start_s)} - {formatTime(rec.end_s)} ({rec.duration_s.toFixed(2)}s)
                            </span>
                        </div>
                        <textarea
                            className="form-control"
                            style={{ width: '100%', minHeight: '60px', padding: '8px', border: '1px solid #ced4da', borderRadius: '4px', resize: 'vertical' }}
                            value={texts[rec.slot] !== undefined ? texts[rec.slot] : (rec.text || '')}
                            onFocus={() => setFocusedSlot(rec.slot)}
                            onChange={(e) => handleChange(rec.slot, e.target.value)}
                        />
                    </div>
                ))}
            </div>
        </div>
    );
}

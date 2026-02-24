import React, { useState, useEffect } from 'react';
import { useJob } from '../../hooks/useJob.jsx';

export function SRTWidget() {
    const { jobId, jobData, setFocusedSlot } = useJob();
    const [texts, setTexts] = useState({});
    const [saving, setSaving] = useState(false);

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
        <div className="card srt-widget" style={{ marginTop: '20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <p className="card-title" style={{ margin: 0 }}>AD-Texte bearbeiten (SRT Ansicht)</p>
                <button
                    className="btn btn-primary"
                    onClick={handleSave}
                    disabled={saving}
                >
                    {saving ? 'Speichert...' : '💾 Änderungen speichern'}
                </button>
            </div>

            <div className="srt-list" style={{ marginTop: '15px', maxHeight: '500px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {jobData.gpt_records.map((rec, idx) => (
                    <div key={idx} style={{ padding: '10px', backgroundColor: '#f8f9fa', border: '1px solid #dee2e6', borderRadius: '4px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '0.9rem', color: '#6c757d' }}>
                            <strong>Slot {rec.slot}</strong>
                            <span>{rec.start_s.toFixed(2)}s - {rec.end_s.toFixed(2)}s ({rec.duration_s.toFixed(2)}s)</span>
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

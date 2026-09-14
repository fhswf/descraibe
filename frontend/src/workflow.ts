// One source for navigation and orchestration; no reserved Qwen/attribute step yet.
export const STEP = { upload: 0, vad: 1, transcribe: 2, slots: 3, images: 4, tracking: 5, identities: 6, gpt: 7, tts: 8, results: 9 } as const;
export const WORKFLOW = [
    { key: 'upload', label: 'Video hochladen' }, { key: 'vad', label: 'Sprechpausen (VAD)' },
    { key: 'transcribe', label: 'Transkription' }, { key: 'slots', label: 'AD-Slots' },
    { key: 'images', label: 'Bilder extrahieren' }, { key: 'tracking', label: 'Tracking & Gesichter' },
    { key: 'identities', label: 'Personen & Cluster' }, { key: 'gpt', label: 'Audiodeskription generieren' },
    { key: 'tts', label: 'Vertonung (TTS)' }, { key: 'results', label: 'Ergebnisse & Download' },
] as const;

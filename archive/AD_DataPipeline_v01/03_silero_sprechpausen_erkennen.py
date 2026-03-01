import json
import torch

def detect_pauses_json(
    audio_path: str,
    sample_rate_hz: int = 16000,
    threshold: float = 0.5,
    min_speech_duration_ms: int = 200,
    min_silence_duration_ms: int = 400,
    speech_pad_ms: int = 50,
    save_path: str | None = None,
) -> str:
    """
    Ermittelt Sprechpausen in einer Audiodatei und liefert sie als JSON-String zurück.
    Optional: Speicherung als JSON-Datei über `save_path`.
    
        Parameter
    ----------
    audio_path : str
        Pfad zur Eingabe-Audiodatei (z. B. WAV).
    sample_rate_hz : int, optional, default=16000
        Samplingrate, auf die die Audiodaten eingelesen werden sollen.
        Das Silero-VAD-Modell ist für 16 kHz optimiert.
    threshold : float, optional, default=0.5
        Schwellwert für die Sprachwahrscheinlichkeit. Höhere Werte machen 
        das Modell strenger beim Erkennen von Sprache.
    min_speech_duration_ms : int, optional, default=200
        Minimale Dauer eines Sprachsegments in Millisekunden. Kürzere Segmente
        werden verworfen.
    min_silence_duration_ms : int, optional, default=400
        Minimale Länge einer Pause in Millisekunden, damit diese als Trennung 
        zwischen Sprachsegmenten gewertet wird.
    speech_pad_ms : int, optional, default=50
        Zusätzliche Millisekunden, die vor und nach jedem erkannten Sprachsegment 
        belassen werden (Polsterung).
    save_path : str | None, optional, default=None
        Falls angegeben, wird das Ergebnis zusätzlich als JSON-Datei unter diesem 
        Pfad gespeichert. Bei None erfolgt keine Speicherung.

    Returns
    -------
    json_str : str
        JSON-String: Liste von Objekten mit pause_index, start_s, end_s, dur_s
    """
    # Silero VAD laden
    model, utils = torch.hub.load('snakers4/silero-vad', 'silero_vad', force_reload=False)
    get_speech_timestamps, _, read_audio, _, _ = utils

    # Audio einlesen (via torch utils)
    wav = read_audio(audio_path, sampling_rate=sample_rate_hz)

    # Sprachsegmente erkennen
    with torch.no_grad():
        speech_ts = get_speech_timestamps(
            wav, model,
            threshold=threshold,
            min_speech_duration_ms=min_speech_duration_ms,
            min_silence_duration_ms=min_silence_duration_ms,
            speech_pad_ms=speech_pad_ms,
        )

    # Pausen aus Lücken zwischen Sprachsegmenten ableiten
    pauses = []
    cursor = 0
    total_len = len(wav)  # in Samples

    for seg in speech_ts:
        if seg['start'] > cursor:
            pauses.append({
                'pause_index': len(pauses) + 1,
                'start_s': round(cursor / sample_rate_hz, 3),
                'end_s': round(seg['start'] / sample_rate_hz, 3),
                'dur_s': round((seg['start'] - cursor) / sample_rate_hz, 3),
            })
        cursor = seg['end']

    # trailing Pause bis Datei-Ende
    if cursor < total_len:
        pauses.append({
            'pause_index': len(pauses) + 1,
            'start_s': round(cursor / sample_rate_hz, 3),
            'end_s': round(total_len / sample_rate_hz, 3),
            'dur_s': round((total_len - cursor) / sample_rate_hz, 3),
        })

    # JSON erzeugen
    json_str = json.dumps(pauses, ensure_ascii=False, indent=2)

    # optional speichern
    if save_path:
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(json_str)

    return json_str



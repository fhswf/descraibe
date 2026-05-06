"""tts_export.py - Generate TTS using OpenAI and mix with original video."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from openai import OpenAI
from moviepy import VideoFileClip, AudioFileClip, CompositeAudioClip
from proglog import ProgressBarLogger

log = logging.getLogger(__name__)

def generate_tts(
    records: List[Dict[str, Any]],
    api_key: str,
    output_dir: Path,
    voice: str = "alloy",
    progress_cb: Optional[Callable[[str, int, int], None]] = None,
) -> Dict[int, str]:
    """Generate TTS for each record and save to output_dir.
    
    Returns a mapping of slot_id -> path_to_tts_file
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    client = OpenAI(api_key=str(api_key).strip())
    
    tts_files = {}
    total = sum(1 for rec in records if rec.get("ok") and not rec.get("skipped") and rec.get("text"))
    current = 0
    
    for rec in records:
        slot_id = int(rec["slot"])
            
        if not rec.get("ok") or rec.get("skipped") or not rec.get("text"):
            continue
            
        if progress_cb:
            progress_cb(f"Generating TTS for Slot {slot_id}...", current, total)
        current += 1
            
        text = rec["text"]
        out_path = output_dir / f"slot_{slot_id}.mp3"
        
        try:
            response = client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=text
            )
            response.stream_to_file(str(out_path))
            tts_files[slot_id] = str(out_path)
            rec["tts_path"] = str(out_path)
        except Exception as exc:
            log.error("Failed to generate TTS for slot %s: %s", slot_id, exc)
            
    if progress_cb:
        progress_cb("TTS Generation completed", total, total)
        
    log.info("TTS generation complete: %s files generated.", len(tts_files))
    return tts_files


class ExportLogger(ProgressBarLogger):
    def __init__(self, on_progress):
        super().__init__()
        self.on_progress = on_progress
        self.current_phase = "Preparing export..."
        self.is_audio = False
        
    def bars_callback(self, bar, attr, value, old_value=None):
        if attr == "index":
            try:
                # Use dict syntax to avoid AttributeError
                total = self.state.get("bars", {}).get(bar, {}).get("total", 1)
                
                # Differentiate audio and video phases in the UI
                phase_msg = "Compositing Audio..." if self.is_audio else "Multiplexing Video..."
                self.on_progress(phase_msg, value, total)
            except Exception:
                pass

            
    def callback(self, **kw):
        msg = kw.get("message", "")
        if not msg:
            return
        lower_msg = msg.lower()
        if "writing audio" in lower_msg or "building audio" in lower_msg:
            self.is_audio = True
            self.current_phase = "Compositing Audio..."
        elif "writing video" in lower_msg or "building video" in lower_msg:
            self.is_audio = False
            self.current_phase = "Multiplexing Video..."


def mix_audio_and_export(
    video_path: str,
    records: List[Dict[str, Any]],
    output_path: str,
    ducking_volume: float = 0.4,
    progress_cb: Optional[Callable[[str, float, float], None]] = None,
) -> str:
    """Mix TTS audio clips into the original video and export.
    
    Args:
        video_path: Path to original video
        records: List of GPT records (must have 'tts_path' and 'start_s')
        output_path: Path to save final MP4
        ducking_volume: Volume multiplier for the original audio track
        progress_cb: Callback (message, current, total)
    """
    log.info("Mixing and exporting AD: video=%s, records=%s, output=%s", video_path, len(records), output_path)
    if progress_cb:
        progress_cb("Loading video and audio tracks...", 0, 100)
        
    video = VideoFileClip(video_path)
    audio_clips = []
    
    if video.audio:
        bg_audio = video.audio.with_volume_scaled(ducking_volume)
        audio_clips.append(bg_audio)
        
    for rec in records:
        if "tts_path" in rec and rec["tts_path"]:
            try:
                clip = AudioFileClip(rec["tts_path"]).with_start(rec["start_s"])
                audio_clips.append(clip)
            except Exception as exc:
                log.error("Failed to load TTS audio from %s: %s", rec["tts_path"], exc)
                
    if progress_cb:
        progress_cb("Setting up audio composite...", 10, 100)
        
    final_audio = CompositeAudioClip(audio_clips)
    final_video = video.with_audio(final_audio)
    
    def cb(msg, cur, total):
        if progress_cb:
            progress_cb(msg, cur, total)

    export_logger = ExportLogger(cb)
    
    final_video.write_videofile(
        output_path, 
        audio_codec="aac",
        logger=export_logger
    )
    
    video.close()
    for c in audio_clips:
        c.close()

    if progress_cb:
        progress_cb("Export completed", 100, 100)
    
    log.info("Export complete: %s", output_path)
    return output_path

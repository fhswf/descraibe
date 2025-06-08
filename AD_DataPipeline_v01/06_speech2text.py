##################################################################
# Projektarbeit Audiodeskription
#
# Modul zur Bildextraktion - (6) Speech2Text - gem. 20250601_DataPipeline_v01.xlsx
#
# Gruppe: Adriana Klaja, Claus-Peter Koch
#
# Version: 0.1.0.0  - 08.06.2025 
#
# !!!!! Testversion für Audiodeskription aus einer MP4 !!!!! 
#
# Testaufruf: python 06_speech2text.py --transkript_lvl="S" - für das kleine Modell und einen schnellen Test mit "Film.mp4"
#
# ToDo: 
# - Überführung in Jupyter Notebook
# - Anpassung an übergebene Daten von anderer Gruppe gemäß Planung - .wav Datei(en)
# - Nur relevante Audiosegmente transkripieren - also nur die mit Sprache 
# -> Lösungsansätze:
#    -- Audiofilter für Musik > Spektrum der Sprache
#    -- Voice Activity Detectors(VAD)
#
# - Sprecher Erkennung - Wer spricht (falls es mehrere Sprecher gibt)
#
##################################################################
'''
# Aufruf der Funktion ermöglicht das Transkripieren von (noch Video) Audio/Sprache in Text
#
# Parameter:
#
# Film: video_path = Pfad zum Film mit Endung .mp4 erwartet
# Ausgabeordner: output_folder = Text Speicherpfad zur Datei
# 
#
# Beispielaufruf: python 06_speech2text.py /Ordner/Datei.mp4        #(noch mp4 - später .wav)
#
# Default Werte: 
# Filmfpad: Film.mp4
# Ausgabedatei: Transkript.txt 
'''

#%pip install --upgrade setuptools wheel
#!pip install --upgrade pip setuptools wheel
#!pip install webrtcvad-wheels
#!pip install webrtcvad

from pydub import AudioSegment
from pydub.utils import which
AudioSegment.converter = "/usr/bin/ffmpeg "#r"D:\ffmpeg\bin\ffmpeg.exe"  # <-- Pfad zu ffmpeg.exe - ist anzupassen
print(which("ffmpeg"))  # Sollte den Pfad zur ffmpeg.exe zurückgeben

import os
import wave
import json
import contextlib
import webrtcvad
import numpy as np
from moviepy import VideoFileClip
from pydub import AudioSegment
import whisper
from datetime import datetime
from datetime import timedelta
import torch
import argparse

import json #optional


# Gerät wählen (automatisch GPU, wenn vorhanden, sonst CPU)
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Nutze Gerät: {device}")
print("Gerät verfügbar: ", torch.cuda.is_available())
print("Gerätname: ", torch.cuda.get_device_name(0))

#Aktuelles Arbeitsverzeichnis ermitteln:
script_dir = os.path.dirname(os.path.abspath(__file__))


def extract_audio(mp4_path, wav_path, sample_rate=16000):
    """ Funktion extrahiert Audio aus MP4, wandelt um zu 16kHz, Mono, 16bit PCM
    
    Args:
        mp4_path = Pfad zur Filmdatei (.mp4)
        wav_path = Pfad zur Ausgabedatei (.WAV)
        sample_rate = Abtastrate (default 16K - für whisper)

    Return:
        True - wenn erfolgreich durchgelaufen
    """
        
    temp_wav = os.path.join(script_dir, "temp_full_audio.wav") # Zwischenspeicher - später löschen (s.u.)

    # MoviePy konvertiert zu WAV (kann Stereo sein)
    video = VideoFileClip(mp4_path)
    video.audio.write_audiofile(temp_wav) #Zwischenspeichern

    # Pydub erzwingt Mono + 16kHz
    sound = AudioSegment.from_file(temp_wav)
    sound = sound.set_channels(1)
    sound = sound.set_frame_rate(sample_rate)
    sound = sound.set_sample_width(2)  # 2 bytes = 16-bit
    sound.export(wav_path, format="wav") #Speichern im passenden Format für whisper

    os.remove(temp_wav) # löschen der temporären Datei
    return(True)



def read_wave(path):
    """ Funktion liest eine .wav Datei ein.

    Args:
        path (str): Pfad zur .wav Datei

    Returns:
        tuple[bytes, int]: Ein Tupel bestehend aus:
            - pcm_data (bytes): Die PCM-Audiodaten der Datei als Byte-String.
            - framerate (int): Die Abtastrate der Datei (sollte 16000 sein für whisper Verarbeitung).
    """
    with contextlib.closing(wave.open(path, 'rb')) as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 16000
        pcm_data = wf.readframes(wf.getnframes())
        return pcm_data, wf.getframerate()


def save_transcript_txt(segments, txt_path="transkript.txt"):
    """
    Speichert ein Transkript bestehend aus Zeitsegmenten und Text in einer Textdatei.

    Die Funktion schreibt jedes Segment in eine neue Zeile des Textdokuments im Format: [START - END: Dauer] TEXT

    Args:
        segments (list[dict]): Liste von Segmenten. Jedes Segment ist ein Dictionary mit den Schlüsseln:
            - 'start' (float): Startzeitpunkt des Segments in Sekunden.
            - 'end' (float): Endzeitpunkt des Segments in Sekunden.
            - 'text' (str): Transkribierter Text des Segments.
        txt_path (str, optional): Pfad zur Zieldatei. Standard ist "transkript.txt".

    Returns:
        True: Die Funktion erzeugt eine Textdatei als Seiteneffekt und gibt True zurück, wenn fertig

    """
    with open(txt_path, "w", encoding="utf-8") as f:
        for seg in segments:
            start = seg['start']
            end = seg['end']
            duration = end - start
            text = seg['text'].strip()
            f.write(f"[{start:06.2f} - {end:06.2f}; {duration:05.2f}] {text}\n")
        return(True)
            
            
            

def transkription_mit_zeitstempel(wav_file,txt_file,mod_lvl="L"):
    """
    Transkripiert eine Audiodatei und speichert Text in einer Textdatei .txt
    
    Args:
        wav_file (str): .wav Datei mit dem zu transkripierendem Audio
        txt_file (str): Ausgabedatei .TXT 
        mod_lvl (str): Modellgröße - default L - large;  s - small ; m - medium
    """
    print("Dieser Vorgang kann einige Minuten dauern! Je nach GPU oder CPU ca. bis zu 50x Videolänge")
    confirm = input("Möchtest du fortfahren? (Y zum Bestätigen): ").strip().lower()
    
    # Bestätigung mit y oder Y
    if confirm.lower() != "y":
        print("Vorgang abgebrochen.")
        return
    
    # OPTIONAL: UPDATE auf WHISPERX <- genauer, nicht unbedingt besser
    #model = whisper.load_model("large")  # oder "small", "medium", ...
    #
    print("Aktuelle Uhrzeit:", datetime.now().strftime("%H:%M:%S")) 
    print("Abbruch mit STRG+C")
    
    if(mod_lvl == "L"):
        model = whisper.load_model("large", device=device)  # nur Modell laden #large # medium
        print("whisper Large Modell wird verwendet! Lange Ausrührungsdauer!")
    elif (mod_lvl == "M"):
        model = whisper.load_model("medium", device=device)  # nur Modell laden #large # medium
        print("whisper medium Modell wird verwendet! Mittlere Ausrührungsdauer - Texte genau kontrollieren!")
    elif (mod_lvl == "S"):
        model = whisper.load_model("small", device=device)  # nur Modell laden #large # medium
        print("whisper small Modell wird verwendet! kurze Ausrührungsdauer - Texte genau kontrollieren - oft weniger gute Texte!")
        
    result = model.transcribe(
        wav_file,
        language="de",
        condition_on_previous_text=False
    )
        
    save_transcript_txt(result["segments"], txt_file)
    print("Aktuelle Uhrzeit:", datetime.now().strftime("%H:%M:%S"))
    print(f"Transkript gespeichert unter: {txt_file}")

# In[17]:

'''
def main(mp4_path):
    wav_path = os.path.join(script_dir, "audio_temp.wav")
    extract_audio(mp4_path, wav_path)

    audio, sample_rate = read_wave(wav_path)
    vad = webrtcvad.Vad(2)
    frames = list(frame_generator(30, audio, sample_rate))
    segments = vad_collector(sample_rate, 30, 300, vad, frames)

    os.remove(wav_path)

    save_segments_to_json(segments)
    print("Unbearbeitete Segmente gespeichert in speech_segments.json")

    # Optional zusammenfassen
    merged = merge_segments(segments, threshold=0.51) #0.25s = 250ms
    
    print("\nZusammengefasste Sprachsegmente:")
    for start, end in merged:
        dauer = end - start
        print(f"{start:.2f} - {end:.2f} - Dauer: {dauer:.2f}s")

    # WAV nochmal erstellen für MP3-Export (falls zuvor gelöscht)
    extract_audio(mp4_path, wav_path)
    export_segments_to_mp3(wav_path, merged, max_count=5)
    os.remove(wav_path)
    
    transkription_mit_zeitstempel("/home/claus/Englands-Biber---Der-Chaos-Effekt_238831350_01_AD.mp4")

'''


if __name__ == "__main__":
    #Skriptverzeichnis ermitteln
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_video_path = os.path.join(script_dir, "Film.mp4")
    default_output_file = os.path.join(script_dir, "FilmBilder")

    # Argumente definieren
    parser = argparse.ArgumentParser(description="(MP4)Audio Transkription Speech-2-Text.")
    parser.add_argument("--wav_file", default=default_video_path, help="Pfad zur .mp4 Datei (Default: Film.mp4 im Skriptverzeichnis) - Später .WAV")
    parser.add_argument("--output_file", default=default_output_file, help="Datei zum Speichern der Transkription (Default: Skriptverzeichnis/Transkription.txt)")
    parser.add_argument("--transkript_lvl", default="L", help="Level des Whisper Modells - L=large; M=medium; S=small")
    
    # Argumente parsen und Funktion starten
    args = parser.parse_args()

    temp_audio = "temp_audio.wav"   #<-- Entfällt bei Anpassung
    extract_audio(mp4_path=args.wav_file, wav_path=temp_audio ) # wird entfernt, sobald .wav als eingabe bereitgestellt wird.

    transkription_mit_zeitstempel(wav_file=temp_audio, txt_file=args.output_file, mod_lvl=args.transkript_lvl) #wav_file=args.wav_file,  <-- Für Anpassung



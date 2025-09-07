#Importieren der benötigten Python-Bibliotheken
#Damit whisper verwendet werden kann, muss das Tool FFmpeg auf der entsprechenden Umgebung installiert sein (https://www.ffmpeg.org/download.html)
import whisper
from pydub.utils import mediainfo
import json

#Funktion zur Bestimmung der Länge einer Audio-Datei
def get_audio_sec_duration(audio_path):
    audio_info = mediainfo(audio_path)

    return float(audio_info['duration'])

#Funktion zum Laden des gewünschten Whisper-Modells
def load_whisper_model(whisper_model_size):
    return whisper.load_model(whisper_model_size)

#Funktion zum Zusammenführen von direkt benachbarten Sprechpausen zu einer größeren Sprechpause
def merge_non_speech_intervals(intervals): 
    non_speech_intervals_merged = []
    i=0

    #Iteration über Sprechpausen
    while i < len(intervals):

        #Start einer Sprechpause
        start = intervals[i]['start']

        if i+1 < len(intervals):

            #Iteration, solange aktuelle Sprechpause nicht direkt an nächste Sprechpause grenzt
            while intervals[i]['end'] == intervals[i+1]['start']:
                i+=1
                #Abbruch bei letzter Sprechpause
                if i+1 == len(intervals):
                    break

        #Ende einer Sprechpause        
        end=intervals[i]['end']

        interval = {
            "start" : format_time_min_sec_ms(start),
            "end" : format_time_min_sec_ms(end),
            "duration" : round(end - start, 3)
        }
        non_speech_intervals_merged.append(interval)

        i+=1

    return non_speech_intervals_merged

#Funktion aus Modul "SpeechToText" zur Einhaltung des SRT-Formats
def format_time_min_sec_ms(input_str):
    """
    Wandelt einen String im Format 'Sekunden.Millisekunden' (z.B. '103.06')
    in 'Minuten:Sekunden:Millisekunden' (z.B. '01:43.060') um.
    """
    try:
        # in float-Sekunden parsen
        total_seconds = float(input_str)
    except ValueError:
        return ""
    # Gesamte Millisekunden
    total_ms = int(round(total_seconds * 1000))
    minutes = total_ms // 60000
    seconds = (total_ms % 60000) // 1000
    milliseconds = total_ms % 1000
    # Formatierung
    return f"{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

#Funktion zur Speicherung der Sprechpausen in einer JSON-Datei
def save_output_to_file(non_speech_intervals):
    output_data = {
        "data" : non_speech_intervals
    }

    with open("NonSpeechIntervals.json", "w") as output_file:
        json.dump(output_data, output_file, indent=4)

#Funktion zur Bestimmung der Sprechpausen in Audio-Dateien
def get_non_speech_intervals(audio_path, whisper_model_size, min_interval_size, is_save_output_file):   
    #Parameter "audio_path": Pfad zu Audio-Datei, bevorzugt .wav-Format für Whisper-Modell
    #Parameter "whisper_model": ("tiny", "base", "small", "medium", "large", "turbo"), bevorzugt "large", da beste Transkriptions-Ergebnisse mit bisherigen Tests
    #Parameter "min_interval_size": Mindestlänge der "Non-Speech-Intervalle" (laut MDR eignen sich auch kurze Intervalle von ca. 1 Sekunde, daher kleiner Wert zu wählen)
    #Parameter "is_save_output_file": Angabe über Wahrheitswert, ob Ausgabe/Sprechpausen in einer JSON-Datei gesichert werden sollen
    
    whisper_model = load_whisper_model(whisper_model_size)

    audio_sec_duration = get_audio_sec_duration(audio_path)

    #Transkription der Audio-Datei mithilfe des Whisper-Modells
    result = whisper_model.transcribe(
        audio_path,
        language='de', 
        condition_on_previous_text=False
    )

    speech_segments = result["segments"]
    non_speech_intervals = []

    #Iteration über alle Transkriptions-Bausteine, um dazwischen liegende Sprechpause zu identifizieren 
    for i in range(0, len(speech_segments)):
        
        #Klassifikation eines Intervalls als Sprechpause, wenn transkribierter Text leer ist oder ausschließlich Musik identifiziert
        if speech_segments[i]['text'] == ' .' or speech_segments[i]['text'] == ' Musik':
            non_speech_interval = {
                "start" : speech_segments[i]['start'],
                "end" : speech_segments[i]['end'],
                "duration" : speech_segments[i]['end'] - speech_segments[i]['start'] 
            }
            non_speech_intervals.append(non_speech_interval)

        #Klassifikation einer Sprechpause am Anfang des Audios (i==0)
        if i == 0 and speech_segments[i]['start'] > 0:
            
            non_speech_interval = {
                "start" : 0,
                "end" : speech_segments[i]['start'],
                "duration" : speech_segments[i]['start'] - 0 
            }
            non_speech_intervals.append(non_speech_interval)

        #Klassifikation einer Sprechpause in der Mitte des Audios (i<letzter Intervall)
        elif i < len(speech_segments) - 1:
            non_speech_interval = {
                "start" : speech_segments[i]['end'],
                "end" : speech_segments[i + 1]['start'],
                "duration" : speech_segments[i + 1]['start'] - speech_segments[i]['end'] 
            }
            non_speech_intervals.append(non_speech_interval)

        #Klassifikation einer Sprechpause am Ende des Audios (i=letzter Intervall)
        elif i == len(speech_segments) - 1 and speech_segments[i]['end'] < audio_sec_duration:
            non_speech_interval = {
                "start" : speech_segments[i]['end'],
                "end" : audio_sec_duration,
                "duration" : audio_sec_duration - speech_segments[i]['end'] 
            }
            non_speech_intervals.append(non_speech_interval)

    #Filterung auf Sprechpausen, die die definierte Mindestlänge (min_interval_sizes) einhalten
    non_speech_intervals_check = [i for i in non_speech_intervals if i['duration'] >= min_interval_size]
    
    #Zusammenfassen der direkt aneinandergrenzenden Sprechpausen
    non_speech_intervals_merged = merge_non_speech_intervals(non_speech_intervals_check)

    #Optionale Speicherung der Sprechpausen in einer JSON-Datei
    if is_save_output_file:
        save_output_to_file(non_speech_intervals_merged)

    return non_speech_intervals_merged

get_non_speech_intervals("[Beispieldatei].[wav|mp3]", "[base]", [0.5], [True])

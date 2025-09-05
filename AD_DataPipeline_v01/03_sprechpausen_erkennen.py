#Importieren der benötigten Python-Bibliotheken
#Damit whisper verwendet werden kann, muss das Tool FFmpeg auf der entsprechenden Umgebung installiert sein (https://www.ffmpeg.org/download.html)
import whisper
from pydub.utils import mediainfo

#Funktion zur Bestimmung der Länge einer Audio-Datei
def get_audio_sec_duration(audio_path):

    audio_info = mediainfo(audio_path)
    return float(audio_info['duration'])


#Funktion zum Laden des gewünschten Whisper-Modells
def load_whisper_model(whisper_model_size):

    return whisper.load_model(whisper_model_size)


#Methode zur Bestimmung der "Non-Speech-Intervalle" in Audio-Dateien
    #Parameter "audio_path": Pfad zu Audio-Datei, bevorzugt .wav-Format für Whisper-Modell
    #Parameter "whisper_model": ("tiny", "base", "small", "medium", "large", "turbo"), bevorzugt "large", da beste Transkriptions-Ergebnisse mit bisherigen Tests
    #Parameter "min_interval_size": Mindestlänge der "Non-Speech-Intervalle" (laut MDR eignen sich auch kurze Intervalle von ca. 1 Sekunde, daher kleiner Wert zu wählen)

def get_non_speech_intervals(audio_path, whisper_model_size, min_interval_size):
    
    whisper_model = load_whisper_model(whisper_model_size)

    audio_sec_duration = get_audio_sec_duration(audio_path)
    
    print(f"Länge der Audio-Datei: {str(audio_sec_duration)} Sekunden")

    #Transkription der Audio-Datei mithilfe des Whisper-Modells
    result = whisper_model.transcribe(
        audio_path,
        language='de', 
        condition_on_previous_text=False
    )

    speech_segments = result["segments"]

    non_speech_intervals = []

    print("Transkription-Bausteine")

    #Iteration über alle Transkriptions-Bausteine, um dazwischen liegende "Non-Speech-Intervalle" zu identifizieren 
    for i in range(0, len(speech_segments)):

        print(f"{i}: {speech_segments[i]}")
        
        #Klassifikation eines Intervalls als "Non-Speech-Intervall", wenn transkribierter Text leer ist oder ausschließlich Musik identifiziert
        if speech_segments[i]['text'] == ' .' or speech_segments[i]['text'] == ' Musik':
            non_speech_interval = {
                "start" : speech_segments[i]['start'],
                "end" : speech_segments[i]['end'],
                "duration" : speech_segments[i]['end'] - speech_segments[i]['start'] 
            }
            non_speech_intervals.append(non_speech_interval)

        #Klassifikation eines "Non-Speech-Intervalls" am Anfang des Audios (i==0)
        if i == 0 and speech_segments[i]['start'] > 0:
            
            non_speech_interval = {
                "start" : 0,
                "end" : speech_segments[i]['start'],
                "duration" : speech_segments[i]['start'] - 0 
            }
            non_speech_intervals.append(non_speech_interval)

        #Klassifikation eines "Non-Speech-Intervalls" in der Mitte des Audios (i<letzter Intervall)
        elif i < len(speech_segments) - 1:
            non_speech_interval = {
                "start" : speech_segments[i]['end'],
                "end" : speech_segments[i + 1]['start'],
                "duration" : speech_segments[i + 1]['start'] - speech_segments[i]['end'] 
            }
            non_speech_intervals.append(non_speech_interval)

        #Klassifikation eines "Non-Speech-Intervalls" am Ende des Audios (i=letzter Intervall)
        elif i == len(speech_segments) - 1 and speech_segments[i]['end'] < audio_sec_duration:
            non_speech_interval = {
                "start" : speech_segments[i]['end'],
                "end" : audio_sec_duration,
                "duration" : audio_sec_duration - speech_segments[i]['end'] 
            }
            non_speech_intervals.append(non_speech_interval)

    #Filterung auf "Non-Speech-Intervalle", die die definierte Mindestlänge (min_interval_sizes) einhalten
    non_speech_intervals_check = [i for i in non_speech_intervals if i['duration'] >= min_interval_size]
    print("Sprechpausen-Intervalle:")
    print(non_speech_intervals_check)

    return non_speech_intervals_check

get_non_speech_intervals("[Beispieldatei].wav", "[large]", [0.5])

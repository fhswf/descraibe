#Bibliotheken importieren
#Damit whisper verwendet werden kann, muss das Tool FFmpeg auf der entsprechenden Umgebung installiert sein (https://www.ffmpeg.org/download.html)
import whisper

#Lösungs-Code
def get_non_speech_intervals(audio_path, whisper_model, audio_sec_duration, min_interval_sizes):
    model = whisper.load_model(whisper_model)

    result = model.transcribe(audio_path)

    speech_segments = result["segments"]

    non_speech_intervals = []

    for i in range(0, len(speech_segments)):
        
        if i == 0 and speech_segments[i]['start'] > 0:
            
            non_speech_interval = {
                "start" : 0,
                "end" : speech_segments[i]['start'],
                "duration" : speech_segments[i]['start'] - 0 
            }
            non_speech_intervals.append(non_speech_interval)

        elif i < len(speech_segments) - 1:
            non_speech_interval = {
                "start" : speech_segments[i]['end'],
                "end" : speech_segments[i + 1]['start'],
                "duration" : speech_segments[i + 1]['start'] - speech_segments[i]['end'] 
            }
            non_speech_intervals.append(non_speech_interval)
        elif i == len(speech_segments) - 1 and speech_segments[i]['end'] < audio_sec_duration:
            non_speech_interval = {
                "start" : speech_segments[i]['end'],
                "end" : audio_sec_duration,
                "duration" : audio_sec_duration - speech_segments[i]['end'] 
            }
            non_speech_intervals.append(non_speech_interval)

        non_speech_intervals_check = [i for i in non_speech_intervals if i['duration'] >= min_interval_sizes]

    return non_speech_intervals_check

#Beispielausführung des Lösungs-Codes
#print(get_non_speech_intervals("Projektarbeit FH/Output_Audio_MDR_2.mp3", "base", 30, 1.5))


#Bibliotheken importieren (alt)
#import librosa

#Lösungs-Code (alt)
#file_path = '/file.wav'
#y, sr = librosa.load(file_path, sr=22050)

#non_silent_intervals = librosa.effects.split(y, top_db=20)

#non_silent_intervals_in_seconds = [(start / sr, end / sr) for start, end in non_silent_intervals]
#print("Non silent intervals (in seconds):", non_silent_intervals_in_seconds)

#silent_intervals = []
#previous_end = 0
#for start, end in non_silent_intervals:
#    if start > previous_end:
#        silent_intervals.append((previous_end / sr, start / sr))
#    previous_end = end

#print("Silent intervals (in seconds):", silent_intervals)

#Bibliotheken importieren
import librosa

#Lösungs-Code
file_path = '/file.wav'
y, sr = librosa.load(file_path, sr=22050)

non_silent_intervals = librosa.effects.split(y, top_db=20)

non_silent_intervals_in_seconds = [(start / sr, end / sr) for start, end in non_silent_intervals]
print("Non silent intervals (in seconds):", non_silent_intervals_in_seconds)

silent_intervals = []
previous_end = 0
for start, end in non_silent_intervals:
    if start > previous_end:
        silent_intervals.append((previous_end / sr, start / sr))
    previous_end = end

print("Silent intervals (in seconds):", silent_intervals)

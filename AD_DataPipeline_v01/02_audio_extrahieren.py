from moviepy import * 

def extract_audio(movie_file):
    audio_track = movie_file.audio
    return audio_track


from moviepy import * 

def extract_audio(movie_file:VideoFileClip):

    """
    Arguments:
        movie_file: in moviepy eingelesenes Video (VideoFileClip)

    Returns:
        Audiospur
    """

    audio_track = movie_file.audio
    return audio_track


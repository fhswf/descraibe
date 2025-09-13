from moviepy import * 

def extract_audio(movie_file:VideoFileClip):

    """
    Arguments:
        movie_file: in moviepy eingelesenes Video (VideoFileClip)

    Returns:
        Audiospur
    """

    try: 
        audio_track = movie_file.audio
        return audio_track
    except AttributeError as error:
        print(f"There was an error due to a non-compatible type being passed to the method. Is the file a VideoFileClip? {error}")
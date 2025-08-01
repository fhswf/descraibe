from moviepy import * 

def load_movie (file_path):

    """
    Arguments:
        file_path: Pfad zur Filmdatei (.mp4)

    Returns:
        Video (VideoFileClip) 
    """
    video = VideoFileClip(file_path)
    return video

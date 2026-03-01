from moviepy import * 

def load_movie (file_path):

    """
    Arguments:
        file_path: Pfad zur Filmdatei (.mp4)

    Returns:
        Video (VideoFileClip) 
    """
    try:
        video = VideoFileClip(file_path)
        return video
    except IOError as error:
        print(f"there was an error trying to parse the data{error}")
    except SyntaxError as error:
        print(f"Error processing path: {error}")

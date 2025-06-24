from moviepy import * 

def load_movie (file_path):
    video = VideoFileClip(file_path)
    return video

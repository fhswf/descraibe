from scenedetect import detect, ContentDetector, save_images,open_video


#video_path = Pfad im Dateisystem, Screenshot Path = Pfad an den die Screenshots der dazugehörigen Timestamps gespeichert werden sollen
def detect_scene_timestamps (video_path, screenshot_path = None): 
    scene_timestamps = detect(video_path, ContentDetector())
    if screenshot_path != None: 
        videostream = open_video(video_path)
        images = save_images(scene_list=scene_timestamps,video=videostream,output_dir=screenshot_path,num_images=1)
        return (scene_timestamps, images)
    else:
        return scene_timestamps
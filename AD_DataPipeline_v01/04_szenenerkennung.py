from scenedetect import detect, ContentDetector, save_images

def detect_scenes (file_path, screenshots = None): 
    
    scenes = detect(file_path, ContentDetector())
    
    if screenshots != None: 
        images = save_images(scenes)
        return (scenes, images)
    else:
        return scenes
    
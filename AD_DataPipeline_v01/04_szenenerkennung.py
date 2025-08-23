from scenedetect import detect, ContentDetector, save_images,open_video

def detect_scene_timestamps (video_path:str, screenshot_path = None): 

    """
    Arguments:
        video_path: Pfad des Videos im Dateisystem (str)
        Optional: 
            Screenshot Path: Pfad an den die Screenshots der dazugehörigen Timestamps gespeichert werden sollen (str). Falls Screnshot_path = None, dann werden keine Screenshots zum Szenenwechsel erzeugt

    Returns:
        Timestamps der Szenenwechsel (list)
        Optional: 
            Standbilder zu Beginn der neuen Szene werden in <Screenshot_path> abgelegt
    """

    try:
        scene_timestamps = detect(video_path, ContentDetector())
        print(type(scene_timestamps))
        if screenshot_path != None: 
            videostream = open_video(video_path)
            images = save_images(scene_list=scene_timestamps,video=videostream,output_dir=screenshot_path,num_images=1)
            return (scene_timestamps, images)
        else:
            return scene_timestamps
    except AttributeError as error:
        print(f"{error}")
    except IOError as error:
        print(f"there was an error trying to parse the data{error}")
    except SyntaxError as error:
        print(f"Error processing path: {error}")
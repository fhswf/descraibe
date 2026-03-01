from scenedetect import SceneManager, ContentDetector, ThresholdDetector, AdaptiveDetector, HistogramDetector, HashDetector, save_images, open_video


def detect_scene_timestamps (video_path:str, screenshot_path = None, frameskip = 0, kernel = AdaptiveDetector(), num_images=1): 

    """
    Arguments:
        video_path: Pfad des Videos im Dateisystem (str)
        Optional: 
            Screenshot Path: Pfad an den die Screenshots der dazugehörigen Timestamps gespeichert werden sollen (str). Falls Screnshot_path = None, dann werden keine Screenshots zum Szenenwechsel erzeugt
            num_images: Anzahl der Bilder, die pro Szenenwechsel erzeugt werden sollen (int). Default = 1
            frameskip: Anzahl Frames, die übersprungen werden sollen (int). verarbeite jeden N+1 frames, wobei N frameskip ist. Verarbeite also nur 1/N+1 Prozent des Videos 
            kernel: Verwendeter Kern für die Erkennung. Erlaubte Werte: Contentdetector(), ThresholdDetector(), AdaptiveDetector(), HistogramDetector(), HashDetector()

    Returns:
        Timestamps der Szenenwechsel (list)
        Optional: 
            Standbilder zu Beginn der neuen Szene werden in <Screenshot_path> abgelegt
    """

    try:

        videostream = open_video(video_path)
        scene_manager = SceneManager()
        scene_manager.add_detector(kernel)
        scene_manager.detect_scenes(videostream,frame_skip=frameskip)
        scene_timestamps = scene_manager.get_scene_list()
        print(type(scene_timestamps))
        if screenshot_path != None: 
            images = save_images(scene_list=scene_timestamps,video=videostream,output_dir=screenshot_path,num_images=num_images)
            return (scene_timestamps, images)
        else:
            return scene_timestamps
    except AttributeError as error:
        print(f"{error}")
    except IOError as error:
        print(f"there was an error trying to parse the data{error}")
    except SyntaxError as error:
        print(f"Error processing path: {error}")



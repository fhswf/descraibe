import os
import cv2
import csv
from scenedetect import detect, ContentDetector, save_images,open_video


# die Funktion kommt von 04_Szenenerkennung.py (Stand 21.07.2025)
#video_path = Pfad im Dateisystem, Screenshot Path = Pfad an den die Screenshots der dazugehörigen Timestamps gespeichert werden sollen
def detect_scene_timestamps (video_path, screenshot_path = None): 
    scene_timestamps = detect(video_path, ContentDetector())
    if screenshot_path != None: 
        videostream = open_video(video_path)
        images = save_images(scene_list=scene_timestamps,video=videostream,output_dir=screenshot_path,num_images=1)
        return (scene_timestamps, images)
    else:
        return scene_timestamps

def extract_midframes(video_path: str, output_dir: str, csv_path: str, scene_list):
    """
    Extrahiert Midframes aus einem Video basierend auf einer Liste erkannter Szenen
    und speichert die Frames sowie deren Zeitstempel in einer CSV-Datei.

    Args:
        video_path (str): Pfad zur Videodatei.
        output_dir (str): Zielverzeichnis zum Speichern der extrahierten Midframe-Bilder.
        csv_path (str): Pfad zur CSV-Datei, in die die Bildinformationen geschrieben werden sollen.
        scene_list (list): Liste von (start, end)-Timecode-Paaren für Szenen aus der vorherigen Szenenerkennung.

    Ergebnis:
        - Speichert pro Szene einen Midframe als JPG-Bild.
        - Erstellt eine CSV-Datei mit: [Scene-Index, Bildname, Timestamp in Sekunden].
    """
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)

    with open(csv_path, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Scene', 'Filename', 'Timestamp (s)'])

        for i, (start, end) in enumerate(scene_list):
            start_frame = int(start.get_frames())
            end_frame = int(end.get_frames())
            mid_frame = (start_frame + end_frame) // 2
            timestamp = mid_frame / fps

            cap.set(cv2.CAP_PROP_POS_FRAMES, mid_frame)
            ret, frame = cap.read()

            if ret:
                filename = f"midframe_scene_{i+1}.jpg"
                out_path = os.path.join(output_dir, filename)
                cv2.imwrite(out_path, frame)

                writer.writerow([i + 1, filename, round(timestamp, 3)])

    cap.release()
    print(f"{len(scene_list)} Midframes gespeichert und CSV erstellt: {csv_path}")


    
# führe die Funktionen aus
videofile_path = "bitte_ersetzen"
scene_ts = detect_scene_timestamps(videofile_path)
extract_midframes(videofile_path, "output/midframes/", "output/midframes_csv/test.csv", scene_ts)

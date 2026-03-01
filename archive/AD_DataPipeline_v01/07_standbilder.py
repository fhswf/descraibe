##################################################################
# Projektarbeit Audiodeskription
#
# Modul zur Bildextraktion - (7) Standbildextraktion - gem. 20250601_DataPipeline_v01.xlsx
#
# Autoren: Claus-Peter Koch, Adriana Klaja
#
# Version: 1.0.0.0  - 08.06.2025 
#
# ToDo: 
# - Überführung in Jupyter Notebook
# - Fehlerbehandlungen u.a. zu kleine ms oder zu große Skalierungen
#
##################################################################
'''
# Aufruf der Funktion ermöglicht das Exportieren von Bildern aus einem Video
#
# >> Einfachster Aufruf zur Umwandlung einer benannten "Film.mp4", im gleichen Ordner wie diese Datei: python 07_standbilder.py
#
# Parameter:
#
# Film: video_path - .mp4 erwartet
# Ausgabeordner: output_folder - Bildspeicherpfad
# Abstand: interval_ms - Entnahmeintervall in Millisekunden
# Bildskalierung: scale_factor - Skalierung des Bildes - 1= Originalbild; 2= 50% Verkleinert; Fließkommazahlen
#
# Beispielaufruf: python export_frames.py urlaub.mp4 bilder/ 750 --scale 2.0
# Default Werte: 
# Filmfpad: Film.mp4
# Bilintercall: 1000ms
# Skalierung: Originalbild
# Ausgabeverzeichnis: /FilmBilder/
'''
#pip install opencv-python
import cv2
import os
import argparse


def extract_frames(video_path: str, output_folder: str, interval_ms: float, scale_factor: float):
    
    #Eingabedaten prüfen
    if not os.path.exists(video_path):
        print(f"Film Datei nicht gefunden: {video_path}")
        return

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps == 0:
        print("Kann FPS nicht ermitteln. 0 ist ungültig!")
        return

    # Warnung anzeigen - Daten kontrollieren vor Ausführung
    images_per_second = round(1000.0 / interval_ms, 2)
    print(f"\nAchtung: Es wird {images_per_second} Bild(er) je Sekunde exportiert.")
    print(f"Zielverzeichnis: {output_folder}")
    print("Der Name der Bilder ist die Entnahmezeit im Film in ms.")
    print("Es muss ausreichend Speicher verfügbar sein!")
    print("Dieser Vorgang kann einige Minuten dauern!")
    confirm = input("Möchtest du fortfahren? (Y zum Bestätigen): ").strip().lower()
    
    # Bestätigung mit y oder Y
    if confirm.lower() != "y":
        print("Vorgang abgebrochen.")
        return

    #Intervallberechnung
    frame_interval = int(round((interval_ms / 1000.0) * fps))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    frame_num = 0
    saved_count = 0

    # Exportieren der Bilder im angegebenen ms Abstand - mit entspr. Bildbenennung
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        if frame_num % frame_interval == 0:
            # Skalierung anwenden
            if scale_factor != 1.0:
                width = int(frame.shape[1] / scale_factor)
                height = int(frame.shape[0] / scale_factor)
                frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)

            # Zeitstempel berechnen und Dateiname setzen
            timestamp_ms = int((frame_num / fps) * 1000)
            output_filename = os.path.join(output_folder, f"frame_{timestamp_ms:08d}ms.jpg")
            cv2.imwrite(output_filename, frame)
            saved_count += 1

        frame_num += 1

    cap.release()
    print(f"\nFertig: {saved_count} Bilder gespeichert in '{output_folder}'.")


if __name__ == "__main__":
    # Skriptverzeichnis ermitteln
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_video_path = os.path.join(script_dir, "Film.mp4")
    default_output_folder = os.path.join(script_dir, "FilmBilder")

    # Argumente definieren
    parser = argparse.ArgumentParser(description="Extrahiere Bilder aus einem Video in bestimmten Abständen.")
    parser.add_argument("--video_path", default=default_video_path, help="Pfad zur .mp4 Datei (Default: Film.mp4 im Skriptverzeichnis)")
    parser.add_argument("--output_folder", default=default_output_folder, help="Ordner zum Speichern der Bilder (Default: FilmBilder im Skriptverzeichnis)")
    parser.add_argument("--interval_ms", type=float, default=1000.0, help="Abstand in Millisekunden zwischen Bildern (Default: 1000)")
    parser.add_argument("--scale", type=float, default=1.0, help="Skalierungsfaktor für Ausgabe (z.B. 1.0, 2.0, 0.5) (Default: 1.0)")

    # Argumente parsen und Funktion starten
    args = parser.parse_args()

    extract_frames(
        video_path=args.video_path,
        output_folder=args.output_folder,
        interval_ms=args.interval_ms,
        scale_factor=args.scale
    )

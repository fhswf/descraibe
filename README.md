# 🧠 Audiodeskriptionen_SS25

Entwicklung einer modularen, KI-gestützten Lösung zur automatisierten Erstellung von Audiodeskriptionen im Rahmen eines Hochschulprojekts, Studiengang *Angewandte Künstliche Intelligenz* (Sommersemester 2025) an der FH Südwestfalen.

---

## 🎯 Zielsetzung

Ziel ist die Entwicklung mehrerer KI-basierter **Data Pipelines**, die aus einem Videofile automatisiert Beschreibungen erzeugen, die als Audiodeskription verwendet werden können. Dabei werden Verfahren wie **Speech-to-Text**, **Szenenerkennung**, **Mid-Frame-Extraktion** und **GPT-4 Vision** kombiniert.

---

## 🗂️ Projektstruktur

```text
Audiodeskriptionen_SS25/
├── AD_DataPipeline_v01/        → Erste vollständige Pipeline
├── AD_DataPipeline_v02/        → Alternative Pipeline (z. B. mit BLIP-2, AutoAD-Zero etc.)
├── shared_utils/               → Wiederverwendbare Module und Helferfunktionen
├── input_data/                 → Eingabedaten wie Videos oder Audiodateien
├── output_data/                → Zwischen- und Endergebnisse
├── notebooks/                  → Jupyter-Experimente, Visualisierungen
├── logs/                       → Ausführungs- und Fehlerprotokolle
├── requirements.txt            → Python-Abhängigkeiten
├── .gitignore                  → Auszuschließende Dateien
└── README.md                   → Diese Übersicht

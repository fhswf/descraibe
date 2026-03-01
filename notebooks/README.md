# 📓 Data Pipeline – Audiodeskriptionen

**Notebook:** `Audiodeskription_Data Pipeline_FINAL.ipynb`

Dieses Notebook implementiert eine vollständige, interaktive Pipeline zur automatisierten Erstellung von Audiodeskriptionen aus Videodateien. Es wurde im Rahmen des Projekts *Audiodeskriptionen SS25* an der FH Südwestfalen entwickelt.

---

## 🔄 Pipeline-Schritte

| Schritt | Beschreibung |
|---------|-------------|
| **1. Video einlesen** | Upload und Validierung der Eingabevideodatei |
| **2. Audio extrahieren** | Extraktion der Audiospur aus dem Video |
| **3. Sprechpausen erkennen** | Silero VAD zur Erkennung von Sprechpausen (potenzielle AD-Slots) |
| **4. Szenenerkennung** | Erkennung von Szenenwechseln im Video |
| **5. Mid-Frame-Extraktion** | Extraktion repräsentativer Frames pro Szene |
| **6. Speech-to-Text** | Transkription des Originaltexts via Whisper |
| **7. Standbilder** | Auswahl der besten Frames pro AD-Slot |
| **8. GPT-4 Vision** | Bildbeschreibung der Frames mit GPT-4 Vision |
| **9. GPT AD-Text** | Generierung der finalen Audiodeskriptionstexte |
| **10. Ergebnisse zusammenführen** | Export der fertigen Audiodeskriptionen |

---

## ⚙️ Konfiguration

Die Pipeline lässt sich über folgende Parameter steuern:

- **GPT-Modell:** Auswahl zwischen verschiedenen Presets (standard, fast, quality)
- **System-Prompt / AD-Regeln:** Anpassbar über die ConfigMap oder direkt im Notebook
- **Few-Shot-Beispiele:** Optional, z.B. für Naturdokumentationen (`naturdoku_few_shots.txt`)
- **Sprechpausen-Schwellenwert:** Mindestlänge eines AD-Slots in Sekunden

---

## 🚀 Ausführung

### Im Jupyter Notebook
```bash
jupyter notebook "Audiodeskription_Data Pipeline_FINAL.ipynb"
```

### Als Webanwendung
Die Pipeline ist vollständig in die Webanwendung [descraibe.fh-swf.cloud](https://descraibe.fh-swf.cloud) integriert.

---

## 📋 Voraussetzungen

```bash
pip install -r ../../requirements.txt
```

Außerdem wird ein gültiger **OpenAI API Key** benötigt (als Umgebungsvariable `OPENAI_API_KEY`).

---

## 📊 Qualitätsbewertung

Zur Bewertung der generierten Audiodeskriptionen steht das separate Notebook zur Verfügung:

`notebooks/Qualitaetsbewertung/AD_Qualitätsnotebook_Pro.ipynb`

Es vergleicht KI-generierte ADs mit manuell erstellten Referenz-ADs (z.B. vom MDR) anhand verschiedener Metriken.

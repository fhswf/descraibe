---

## 🎯 Qualitätsnotebook – Automatisierte Bewertung von Audiodeskriptionen

Das **Qualitätsnotebook** erweitert das Projekt *Audiodeskriptionen_SS25* um ein
interaktives Evaluations- und Vergleichs-Tool zur Qualitätsanalyse von Audiodeskriptionen
zwischen **MDR-Referenztexten** und **KI-generierten Hypothesen**.

### ⚙️ Funktionsumfang
- **Segmentierung & Alignment:** Automatisches Zuordnen von Sätzen (TF-IDF + Cosine Similarity)
- **Qualitätsmetriken:** BLEU-1..4, ROUGE-1/2/L, SBERT-Cosine, BERTScore-F1
- **RAGAS-Kennzahlen:** semantic_similarity, answer_similarity, coverage, faithfulness, conciseness, fluency (FRE)
- **Heuristiken:** Erkennung von Farb- und Bewegungsverben (lemma-basiert)
- **Lesbarkeits- und Tempomessung:** Silben- und Wortlängen-Verhältnisse (`len_ratio`, `syl_ratio`)
- **Interaktive Oberfläche:** Tabs für *Text, Qualität, ROUGE-Details, Länge & Abdeckung, Alignment, RAGAS, Alle, Einstellungen*
- **Automatische Rubrikbewertung (MDR-Style):** Stil, Lesehärte, visuelle Klarheit, Handlungsführung, Kohärenz
- **Exportfunktionen:** Markdown- und TXT-Report mit Kennzahlen und Bewertungen

### 🧩 Aufbau
Das Notebook ist modular konzipiert und kann mit den bestehenden Komponenten des Projekts kombiniert werden:
- **Input:** MDR- und KI-Textdateien (`.txt`)  
- **Berechnung:** integriert in die bestehende Pipeline  
- **Visualisierung:** Jupyter-basiertes Dashboard mit einheitlichem Layout  
- **Output:** Markdown-Report oder segmentweiser TXT-Export

📄 **Datei:** [📘 Qualitätsbewertung Notebook](./AD_Qualitätsnotebook_Pro.ipynb)

### 🖼️ Beispiel-Screenshot
(notebooks/Qualitaetsbewertung/assets/dashboard_vorschau.png)

---

### 👥 Autoren & Beitrag
Dieses Modul wurde im Rahmen des Projekts **„Audiodeskriptionen_SS25 – Entwicklung einer KI-Lösung zur Erstellung von Audiodeskriptionen“** an der **Fachhochschule Südwestfalen (FH SWF)** entwickelt.

**Team:**  
Projektteam Audiodeskriptionen_SS25

---

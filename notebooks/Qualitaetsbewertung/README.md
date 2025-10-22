## 🎯 Qualitätsnotebook – Automatisierte Bewertung von Audiodeskriptionen

Das **Qualitätsnotebook** erweitert das Projekt *Audiodeskriptionen_SS25* um ein interaktives Evaluations- und Vergleichs-Tool zur **qualitativen Analyse von Audiodeskriptionen** zwischen **MDR-Referenztexten** und **KI-generierten Hypothesen**.

---

### ⚙️ Funktionsumfang

- **Segmentierung & Alignment:** automatische Zuordnung von Sätzen (TF-IDF + Cosine Similarity)  
- **Kernmetriken:** BLEU-1..4, ROUGE-1/2/L, SBERT-Cosine, BERTScore-F1  
- **RAGAS-Kennzahlen:** semantic_similarity, answer_similarity, coverage, faithfulness, conciseness, fluency (FRE) – mit Fallbacks bei fehlender Bibliothek  
- **Heuristiken:** Erkennung von Farb- und Bewegungsverben (lemma-basiert mit spaCy-Fallback)  
- **Längen- und Lesbarkeitsmaße:** Silben- und Wortverhältnisse (`len_ratio`, `syl_ratio`) sowie Flesch-Amstad-Lesbarkeitsindex  
- **Timing-Analyse:** Berechnung von Start-, End- und Mittel-Abweichungen (Δ-Werte), Overlap-Anteil und *Timing Accuracy*  
- **Interaktive Oberfläche:** Tabs für *Text*, *Qualität*, *ROUGE-Details*, *Länge & Abdeckung*, *Alignment*, *RAGAS*, *Alle*, *Einstellungen* – mit Ampel-Darstellung  
- **Automatische Rubrikbewertung (MDR-Style):** Stil/Konzision, Lesehärte, visuelle Klarheit, Handlungsführung, Inhaltsdeckung & Gesamtnote  
- **Exportfunktionen:** Markdown- und TXT-Reports mit Kennzahlen, Rubrics und Handlungsempfehlungen  

---

### 🧩 Aufbau & Integration

Das Notebook ist modular aufgebaut und lässt sich direkt in bestehende Komponenten des Projekts integrieren:

| Komponente | Beschreibung |
|:------------|:-------------|
| **Input** | MDR- und KI-Texte (`.txt`) |
| **Berechnung** | integriert in die bestehende Pipeline (Segmentierung → Alignment → Bewertung) |
| **Visualisierung** | Jupyter-basiertes Dashboard mit einheitlichem Layout |
| **Output** | Markdown-Report oder segmentweiser TXT-Export |

📄 **Notebook:** [📘 AD_Qualitätsnotebook_Pro.ipynb](./AD_Qualitätsnotebook_Pro.ipynb)

---

### 🧠 Zielsetzung

Das Notebook bietet ein reproduzierbares, metrisch fundiertes Verfahren zur **objektiven Qualitätsbewertung** von Audiodeskriptionen.  
Es kombiniert linguistische, semantische, stilistische und zeitliche Metriken in einer einheitlichen Oberfläche und liefert sowohl **numerische Kennzahlen** als auch **qualitative Interpretationen**.

---

### 👥 Autoren & Beitrag

Entwickelt im Rahmen des Projekts **„Audiodeskriptionen_SS25 – Entwicklung einer KI-Lösung zur Erstellung von Audiodeskriptionen“** an der **Fachhochschule Südwestfalen (FH SWF)**.

**Projektteam:** Audiodeskriptionen_SS25

---

### 📜 Lizenz

Dieses Notebook ist ausschließlich zu **Forschungs- und Lehrzwecken** bestimmt.  
Eine kommerzielle Nutzung oder Weiterverbreitung bedarf der schriftlichen Genehmigung der Autor:innen.

---

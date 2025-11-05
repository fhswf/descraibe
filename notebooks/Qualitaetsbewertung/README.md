## 🎯 AD-Qualitätsnotebook Pro – Automatisierte Bewertung von Audiodeskriptionen

Das **AD-Qualitätsnotebook Pro** ist Teil des Projekts *Audiodeskriptionen_SS25* und dient der interaktiven **Qualitätsanalyse von Audiodeskriptionen** zwischen  
**MDR-Referenztexten** und **KI-generierten Hypothesen**.

---

### ⚙️ Funktionsumfang

- **Segmentierung & Alignment:** automatische Satz-Zuordnung (*TF-IDF + Cosine Similarity*, optional *time_aware_alignment* mit Zeitfenster)
- **Kernmetriken:** BLEU-1 … 4 · ROUGE-1/2/L · SBERT-Cosine · BERTScore-F1  
- **RAGAS-Metriken:** *semantic_similarity*, *answer_similarity*, *faithfulness*, *coverage*, *conciseness*, *fluency (FRE)* – mit Fallbacks, falls Bibliotheken fehlen  
- **Heuristiken:** automatische Erkennung von **Farb- und Bewegungsverben** (lemma-basiert mit *spaCy*-Fallback)
- **Längen- & Lesbarkeitsmaße:** Wörter, Silben, *len_ratio*, *syl_ratio*, Flesch-Amstad-Index  
- **Timing-Analyse:** Start-, End-, Mittel-Δ-Werte, Overlap, *Timing Accuracy* und grafische Darstellung  
- **Rubric-Bewertung (MDR-Style):** Stil/Konzision, Lesehärte, visuelle Klarheit, Handlungsführung, Inhaltsdeckung, Timing-Genauigkeit und Gesamtnote  
- **Streuungs-Analyse:** Variationskoeffizient (CV %) zur Beurteilung der Segmentstabilität  
- **Interaktive Oberfläche:** Tabs für *Text*, *Qualität*, *ROUGE*, *Länge & Abdeckung*, *Alignment*, *Timing*, *Rubrics*, *RAGAS*, *Alle*, *⚙️ Einstellungen* – mit Ampel-Visualisierung  
- **Exportfunktionen:** Markdown-, TSV- und optional Excel-Reports mit Kennzahlen, Rubrics und Empfehlungen  

---

### 🧩 Aufbau & Integration

| **Komponente** | **Beschreibung** |
|:----------------|:-----------------|
| **Input** | MDR- und KI-Texte (`.txt`) |
| **Berechnung** | vollintegrierte Pipeline (Segmentierung → Alignment → Bewertung → Rubrics) |
| **Visualisierung** | Jupyter-Dashboard mit Sticky-Header, Scroll-Container (72 vh) |
| **Output** | Markdown-Report, TSV oder segmentweiser TXT-Export |

📄 **Notebook:** [📘 AD_Qualitaetsnotebook_Pro.ipynb](./notebooks/Qualitaetsbewertung/AD_Qualitaetsnotebook_Pro.ipynb)

---

### 🧠 Zielsetzung

Das Notebook bietet ein **reproduzierbares, metrisch fundiertes Verfahren** zur **objektiven Qualitätsbewertung** von Audiodeskriptionen.  
Es kombiniert linguistische, semantische, stilistische und zeitliche Kennzahlen in einer einheitlichen Oberfläche und liefert sowohl **numerische Ergebnisse**  
als auch **qualitative Interpretationen & Rubric-Noten**.

---

### 👥 Autoren & Beitrag

Entwickelt im Rahmen des Projekts **„Audiodeskriptionen_SS25 – KI-gestützte Erstellung und Evaluation von Audiodeskriptionen“**  
an der **Fachhochschule Südwestfalen (FH SWF)**.

**Projektteam:** *Audiodeskriptionen_SS25*

---

### 📜 Lizenz

Dieses Notebook ist ausschließlich für **Forschung und Lehre** bestimmt. Eine kommerzielle Nutzung oder Weitergabe erfordert die **schriftliche Genehmigung** der Autor:innen.

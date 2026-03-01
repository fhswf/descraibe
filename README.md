# 🧠 Audiodeskriptionen_SS25

Entwicklung einer modularen, KI-gestützten Lösung zur automatisierten Erstellung von Audiodeskriptionen im Rahmen eines Hochschulprojekts, Studiengang *Angewandte Künstliche Intelligenz* (Sommersemester 2025) an der FH Südwestfalen.

---

## 🎯 Zielsetzung

Ziel ist die Entwicklung einer KI-basierten **Data Pipeline**, die aus einer Videodatei automatisiert Audiodeskriptionen erzeugt. Dabei werden Verfahren wie **Speech-to-Text**, **Szenenerkennung**, **Mid-Frame-Extraktion** und **GPT-4 Vision** kombiniert.

---

## 🗂️ Projektstruktur

```text
Audiodeskriptionen_SS25/
├── notebooks/                          → Finale Jupyter Notebooks
│   ├── Audiodeskription_Data Pipeline_FINAL.ipynb  → Hauptpipeline
│   └── Qualitaetsbewertung/
│       └── AD_Qualitätsnotebook_Pro.ipynb           → Qualitätsbewertung
├── webapp/                             → Webanwendung (DescrAIbe)
│   ├── backend/                        → Python/FastAPI Backend
│   ├── frontend/                       → React Frontend
│   └── k8s/                            → Kubernetes Konfiguration
├── archive/                            → Archivierte Entwicklungsskripte
│   └── AD_DataPipeline_v01/            → Frühe Einzelskripte der Studierenden
├── data/                               → Beispieldaten
├── .github/workflows/                  → CI/CD Pipelines
├── requirements.txt                    → Python-Abhängigkeiten
└── README.md                           → Diese Übersicht
```

---

## 📓 Notebooks

### 1. Audiodeskription Data Pipeline (FINAL)
**Pfad:** `notebooks/Audiodeskription_Data Pipeline_FINAL.ipynb`

Die vollständige, interaktive Pipeline zur automatisierten Erstellung von Audiodeskriptionen. Enthält alle Schritte von der Videoeingabe bis zur fertigen Audiodeskription.

→ Siehe [README der Data Pipeline](notebooks/README.md)

### 2. AD-Qualitätsnotebook Pro
**Pfad:** `notebooks/Qualitaetsbewertung/AD_Qualitätsnotebook_Pro.ipynb`

Werkzeug zur Qualitätsbewertung generierter Audiodeskriptionen durch Vergleich mit manuell erstellten Referenz-ADs (MDR ↔ KI).

---

## 🌐 Webanwendung (DescrAIbe)

Die Pipeline ist als vollständige Webanwendung unter [descraibe.fh-swf.cloud](https://descraibe.fh-swf.cloud) verfügbar. Sie basiert auf einem FastAPI-Backend und einem React-Frontend und wird über Kubernetes/ArgoCD betrieben.

→ Weitere Infos: [webapp/README.md](webapp/README.md)

---

## 🛠️ Installation

```bash
git clone https://github.com/fhswf/Audiodeskriptionen_SS25.git
cd Audiodeskriptionen_SS25
pip install -r requirements.txt
```

---

## 📦 Archiv

Unter `archive/AD_DataPipeline_v01/` befinden sich die frühen Entwicklungsskripte der Studierenden (Einzelskripte je Pipeline-Schritt). Diese sind nicht mehr aktiv, dienen aber als Referenz für die Entwicklungsgeschichte des Projekts.

---

## 🏫 Projektkontext

| | |
|---|---|
| **Hochschule** | FH Südwestfalen |
| **Studiengang** | Angewandte Künstliche Intelligenz |
| **Semester** | Sommersemester 2025 |
| **Betreuer** | Prof. Dr. Christian Gawron |

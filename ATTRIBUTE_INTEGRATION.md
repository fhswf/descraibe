# Attributintegration – Stand 15.09.2026

Implementiert auf `codex-person-review`, ohne Commit. Ausgangsstand: `5f5dfd932a6ab704bb6808c73fcde68e1b64d059`.

## Ablauf und Datenquellen

1. Tracking & Gesichter und Personen & Cluster bleiben fachlich unverändert.
2. Attribute liest den aktiven Identity-Run und die wirksamen manuellen Zuordnungen über `review_state.read`. Gesplittete Segmente sind eigene logische Tracks; unassigned Tracks werden ignoriert.
3. Kandidaten sind ausschließlich vorhandene saubere Personencrops aus Tracking- und Identity-Artefakten. Vorhandene Fallback-Crops werden verwendet, wenn ein Track keine geeigneten normalen Crops hat. Keine JPEG-Duplikation und keine Rekonstruktion aus dem Video. Das Video wird nur für Hash und Frameabmessungen geöffnet.
4. `quality_usable` und Face-Exclusions sind keine Attributfilter. Mindesthöhe 15 %, Referenzbewertung 50 % Personenschärfe, 30 % Größe, 20 % Randfreiheit. Ein Repräsentant pro logischem Track, erneute Bewertung der Repräsentanten, maximal fünf Bilder pro Person, chronologisch sortiert.
5. Ohne geeignetes Bild: `no_eligible_images`, kein Qwen-Aufruf. Unlesbare vorhandene JPEGs führen zu einem ausdrücklichen Fehler statt Rekonstruktion.
6. Qwen wird einmal pro Lauf geladen, falls mindestens eine Person Bilder hat. Alle Bilder einer Person gehen gemeinsam in einen Aufruf. Referenzprompt, zwölf Felder, Parser und Generationseinstellungen sind übernommen. Generierungs-/Parserfehler werden pro Person gespeichert und stoppen andere Personen nicht. Ein Modell-Ladefehler aktiviert keinen neuen Lauf.
7. Der Workflow setzt Attribute zwischen Personen & Cluster und AD. Run All führt die drei Personenstufen ohne manuelle Bestätigung aus und übergibt danach an die bestehende AD-/TTS-Kette.

## Persistenz und Stale

Unter `person_analysis/runs/<attribute-run-id>/attributes/`:

- `selection.json`: Auswahl mit stabilen Crop-IDs und relativen Pfaden, Frame/Track/Zeit/BBox, Scores, Videoabmessungen und Herkunft.
- `attributes.json`: automatische zwölf Werte, unveränderte rohe Qwen-Ausgabe, Status/Fehler je Person, Prompt/Modell/Generationsparameter und Herkunft.

`person_analysis/attribute_state.json` zeigt auf den letzten erfolgreich aktivierten Attributlauf.
`review_state.json` enthält optional `attribute_reviews[attribute-run-id]` mit Revision, Parent-Identity-Run und Feld-Overrides je Person. Automatische Dateien werden durch Korrekturen nicht überschrieben. `null` im PATCH setzt ein Feld auf den automatischen Wert zurück. Versionsprüfung verhindert verlorene Updates.

Die Herkunft umfasst Tracking-Run, Identity-Run, Analysis-ID und Hash der wirksamen Trackzuordnungen. Neue Cluster, Splits/Face-Korrekturen mit veraltetem Identity-Run und geänderte Personenzuordnungen machen Attribute stale. Historische Werte bleiben als veraltet sichtbar; Bearbeitung ist dann gesperrt. Ein neuer Lauf übernimmt keine alten Overrides. Reine Namens-/Beschreibungsänderungen erfordern keine neue Inferenz.

Alte Jobs bleiben lesbar. Für Attribute benötigen sie zuerst die neuen Tracking-/Identity-Artefakte. Es gibt keine automatische Migration alter CSVs und keine stille Zuordnung alter Attribute. Die UI weist auf die nötige Neuberechnung hin.

## Routen

- POST/GET `/api/jobs/{job_id}/person-analysis/attributes`
- PATCH `/api/jobs/{job_id}/person-analysis/attribute-review`
- GET `/api/jobs/{job_id}/person-analysis/attributes/{run_id}/images/{crop_id}`

## Dateien

Neu:

- `backend/pipeline/persons/attribute_selection.py`
- `backend/pipeline/persons/qwen_attributes.py`
- `backend/pipeline/persons/attribute_stage.py`
- `backend/pipeline/persons/attribute_state.py`
- `backend/tests/test_attribute_pipeline.py`
- `frontend/src/components/features/StepAttributes.tsx`
- `ATTRIBUTE_INTEGRATION.md`

Geändert:

- `backend/app.py` – neue Routen, zusätzlicher Jobstatus
- `backend/session_manager.py` – gesperrtes Speichern von Attributkorrekturen
- `backend/pipeline/persons/review_artifacts.py` – Original-Personenbbox an Crop-Metadaten weitergeben
- `backend/tests/person_review_server.py` – isoliertes Qwen-Double
- `backend/tests/person_stages_browser.cjs` – Attribute in Run All, UI und Reload
- `frontend/src/App.tsx`
- `frontend/src/hooks/useJob.tsx`
- `frontend/src/types/index.ts`
- `frontend/src/workflow.ts`
- `pyproject.toml`
- `uv.lock`

## Dependencies

Direkt deklariert: `transformers==5.17.0` (bereits vorhandene Version) und `accelerate==1.12.0`.
Neu im Lock: Accelerate 1.12.0 und dessen notwendige transitive Dependency `psutil==7.2.2`.
Ein programmatischer Vergleich bestätigt: keine vorhandene Lock-Paketversion entfernt/geändert. uv hat einige redundante Plattform-/Python-Marker normalisiert.
Nur `uv lock` ausgeführt, kein `uv sync`. Torch und Transformers wurden weder installiert noch aktualisiert. Separate Testwerkzeuge liegen außerhalb des Repositories in der isolierten Codex-Testumgebung.

## Validierung

Abschließende gezielte Backend-Suite: **151 bestanden**, vier Deprecation-Warnungen der isolierten Testwerkzeuge. Enthaltene Dateien:

`test_attribute_pipeline.py`, `test_person_stages.py`, `test_person_review.py`, `test_person_representative.py`, `test_person_evidence.py`, `test_person_crop_storage.py`, `test_track_segments.py`, `test_gpt_model_config.py`, `test_gpt_error_handling.py`, `test_session_manager.py`, `test_store.py`, `test_event_bus.py`, `test_ad_slots.py`.

Die neun neuen Attributtests decken Auswahl, Fallbacks, Exclusions/Qualitätsflags, Splits, Fehlerisolation, fehlende Bilder, Modell-Ladefehler, Stale, Raw/Overrides, API-Bilder, Konflikte, Reset, Cache-Neuladen und einen frischen Python-Prozess ab.

Browser mit Edge/Playwright und echten lokalen API/SSE/Video-Dateien, Modell-Double:

- `person_stages_browser.cjs`: bestanden, einschließlich Tracking → Identity → Attribute → AD-Übergabe, zwölf Felder, JPEG-Anzeige, Overrides/Speichern/Reload/Reset und bestehender Personen-/Split-Reviews.
- `person_review_browser.cjs`: bestanden, Legacy-Review unverändert benutzbar.
- AD wird im Browserfixture abgefangen; kein externer AD-/TTS-Aufruf.

Frontend: `npm run type-check`, `npm run lint`, Vite-Produktionsbuild bestanden. Kein npm-Testskript vorhanden.
`git diff --check` bestanden. AST-Abgleich der sechs Auswahlfunktionen sowie Parser und Nachrichtenaufbau mit den Referenzen bestanden.

Breiterer Testversuch ausdrücklich **nicht grün**: vollständige Sammlung scheiterte zunächst an fehlendem `soundfile` in der isolierten Umgebung. Ohne beide VAD-Testdateien: 187 bestanden, 40 fehlgeschlagen, vier Setupfehler. Befunde umfassen fehlendes `scenedetect`, nicht beschreibbares Standard-Testverzeichnis `/tmp/ad_jobs`, Tests auf entfernte alte Personen-APIs sowie einen Encoding-Vergleich in `test_export.py`. Diese Bereiche wurden nicht repariert. Die gezielte abschließende Suite verwendet ein beschreibbares isoliertes Jobverzeichnis.

## Reale Qwen-Inferenz und offene Punkte

Der Nutzer hat den erfolgreichen echten Modell-Ladetest mit AutoProcessor/AutoModelForMultimodalLM, Transformers 5.17.0, Torch 2.11.0+cu128, Accelerate 1.12.0 und RTX 5070 bestätigt. `hf_device_map` wird nicht verwendet.
**Kein realer Qwen-Inferenztest in dieser Implementierungssitzung.** Die Backend-/Browserprüfungen verwenden Modelldoubles. Die vorhandene CUDA-Umgebung war aus dieser Agent-Shell nicht ausführbar; sie wurde nicht verändert. Reale Attributqualität, Laufzeit und VRAM sind lokal noch zu prüfen.

## Manuelle Browserprüfung

1. Einen Job mit aktuellen Tracking- und Identity-Artefakten öffnen; Attribute ausführen.
2. Auswahlbilder und alle zwölf automatischen Werte prüfen. Ohne geeignete Bilder muss der entsprechende Status erscheinen.
3. Zwei Felder ändern, gemeinsam speichern, Browser und Backend neu starten: Korrekturen müssen erhalten bleiben, automatische Werte weiterhin separat sichtbar sein.
4. Ein Feld zurücksetzen: automatischer Wert wird wieder wirksam.
5. Einen Track umzuordnen oder Cluster erneut ausführen: bisherige Attribute müssen als veraltet markiert und für Änderungen gesperrt sein. Attribute neu ausführen: neuer Lauf ohne alte Overrides.
6. Bei einem neuen Job Run All verwenden: optionale Reviews dürfen die automatische Kette nicht unterbrechen.

Upload, bestehende AD-Prompts, AD-Generierung, TTS, Ergebnisse, RF-DETR, ByteTrack, RetinaFace, FaceMoE und Clustering wurden fachlich nicht verändert. Neue Attribute werden nicht in AD-Prompts oder den bestehenden Personen-DataFrame für AD eingespeist. Keine Embeddings werden zusätzlich gespeichert.

# LichtFeld Studio Webinterface Implementation Plan

> Für Hermes: Dies ist ein Planungsdokument. Noch keine Implementierung starten, bis die offenen Fragen beantwortet sind.

Goal: Ein im RunPod-Container mitgeliefertes Webinterface für LichtFeld Studio bauen, das Training, Monitoring, Dataset-Auswahl, Logs und Export bedienbar macht und sich visuell/strukturell an der Desktop-GUI orientiert.

Architecture: Das Webinterface läuft als zusätzlicher Service im Container auf einem HTTP-Port, z.B. 7860. Ein kleiner Backend-Service verwaltet Dataset-Scan, Training-Prozess, Logs, GPU-Status und Export-Artefakte. Die UI ist eine dunkle, desktopähnliche Single-Page-App mit linker Seitenleiste, zentralem Status/Preview-Bereich und rechter Parameter-/Job-Spalte. Für MVP wird LichtFeld über die vorhandene CLI gestartet; wenn die eingebaute MCP/HTTP-Schnittstelle im Headless-Betrieb zuverlässig verfügbar ist, wird sie als zweite Integrationsschicht ergänzt.

Tech Stack Vorschlag:
- Backend: Python FastAPI + Uvicorn, weil Python bereits im Image vorhanden ist und Prozess-/Log-/Filesystem-Integration einfach ist.
- Frontend: Vite + React + TypeScript oder alternativ statisches HTML/JS ohne Build-Step. Empfehlung: React/TypeScript für sauberen State, Komponenten und spätere Erweiterung.
- Realtime: Server-Sent Events oder WebSocket für Logs, Training-Status und GPU-Snapshots.
- Container: zusätzlicher Service in runpod-start.sh, Port 7860 exposed, Logs unter /workspace/logs/webui.log.

## Design-Ziel

Die Weboberfläche soll nicht wie ein generisches Admin-Panel wirken, sondern wie eine reduzierte Web-Variante von LichtFeld Studio:

- dunkles technisches UI
- klare Trennung: Scene/Dataset, Training, Output/Export, Logs
- sichtbarer Runtime-Zustand statt versteckter Kommandozeilenparameter
- GPU/Iteration/Loss/ETA prominent
- schnell bedienbare Presets statt überladener Formulare
- Desktop-GUI-Anlehnung über Layout und Begriffe, aber keine 1:1-Kopie ohne Screenshots/Assets



## Geklärte Entscheidungen nach User-Feedback

- Klärung künftig dialogisch: immer nur eine Frage stellen und auf Antwort warten.
- Vorgehen: empfohlener MVP-Ansatz ist akzeptiert.
- Dataset-Normalfall: COLMAP-Projekte unter `/workspace/data`; MVP optimiert auf COLMAP statt loose-images-first.
- Designreferenz: Screenshot `Screenshot 2026-05-24 151438.jpg` im Projektverzeichnis vorhanden.

## Screenshot-Analyse: LichtFeld Studio Desktop-GUI

Quelle: `Screenshot 2026-05-24 151438.jpg`

Wichtige visuelle Merkmale:

- Gesamtwirkung: dunkles technisches 3D-Tool, nicht klassisches Web-Dashboard.
- Top-Level: native Menüleiste mit `File`, `Edit`, `Tools`, `View`, `Help`.
- Hauptfläche: großer schwarzer 3D-Viewport mit feinem Perspektiv-Grid, roten/blauen Achsenlinien, gestrichelter Drop-Zone und zentralem Import-Hinweis.
- Linke Werkzeugleiste: schmale vertikale Icon-Bar mit quadratischen aktiven Zuständen; aktive Tools werden hellblau markiert.
- Oberes Viewport-Toolbar: schwebende kompakte Toolgruppe mit Icons für Auswahl/Transform/Navigation.
- Rechts oben: Scene/History/Logging Tabs mit Suchfeld und leerem Scene-State.
- Rechts unten: Rendering/Training Tabs und akkordeonartige Einstellgruppen.
- Controls: kompakte Slider, Selects, Checkboxen, kleine numerische Felder; wenig Weißraum, hohe Informationsdichte.
- Akzentfarbe: kühles Blau/Cyan für aktive Tabs, Slider-Füllungen und Highlights.
- Statusbar unten: links Scene-State (`Empty`), rechts GPU/VRAM/FPS/Version bzw. Commit-Info.

Übernahme für WebUI-MVP:

- AppShell mit großem zentralem Viewport-artigem Arbeitsbereich statt generischem Dashboard-Hero.
- Linke Icon-Navigation für Dashboard/Datasets/Training/Outputs/Logs.
- Rechte Inspector-Spalte mit Tabs `Scene`, `Training`, `Logging`.
- Zentrale Drop-/Importfläche für COLMAP-Datasets; bei WebUI zusätzlich Dataset-Karten und Start-CTA.
- Unten Statusbar mit Pod/GPU/VRAM/Job-State.
- Dunkle Panels, blaue aktive States, kompakte Formcontrols.
- Training-Parameter als Accordion-Gruppen analog `Rendering`, `Camera & Projection`, etc.

Nicht im MVP nachbauen:

- Vollwertiger 3D-Viewport mit Splat-Rendering.
- Exakte Desktop-Menüstruktur.
- Komplette Tool-Icon-Funktionalität ohne dahinterliegende Funktionen.


## MVP-Funktionsumfang

### 1. Service-Integration im Container

Files:
- Create: `webui/backend/app.py`
- Create: `webui/backend/requirements.txt`
- Create: `webui/frontend/...` oder `webui/static/...`
- Modify: `Dockerfile`
- Modify: `runpod-start.sh`
- Modify: `RUNPOD_FEATURES.md`
- Modify: `README.md`

Akzeptanz:
- Container startet optional WebUI-Service auf Port 7860.
- Env-Flag `RUNPOD_ENABLE_LICHTFELD_WEBUI=1|0`.
- Env `RUNPOD_LICHTFELD_WEBUI_PORT=7860`.
- Logs: `/workspace/logs/lichtfeld-webui.log`.
- Start des Containers bleibt robust, auch wenn WebUI nicht startet.

### 2. Backend-Grundgerüst

Endpoints:
- `GET /api/health`
- `GET /api/version`
- `GET /api/config`
- `GET /api/gpu`
- `GET /api/datasets`
- `GET /api/jobs/current`
- `POST /api/train/start`
- `POST /api/train/stop`
- `GET /api/logs/train/stream`
- `GET /api/files/outputs`

Akzeptanz:
- Health zeigt WebUI-Version, LichtFeld-Pfad, Workspace-Pfade.
- GPU-Endpunkt parst `nvidia-smi --query-gpu=... --format=csv,noheader,nounits`.
- Dataset-Endpunkt erkennt COLMAP-Strukturen unter `/workspace/data`.
- Training kann gestartet werden, ohne Shell-Kommando manuell zu tippen.

### 3. Dataset-Erkennung

Erkennung:
- gültiges Dataset, wenn Ordner enthält:
  - `images/`
  - `sparse/0/cameras.bin|cameras.txt`
  - `sparse/0/images.bin|images.txt`
- lose Bilder erkennen und als “Needs COLMAP” markieren.

Backend-Modell:
- path
- name
- type: `colmap | loose_images | unknown`
- image_count
- has_sparse
- warnings

Akzeptanz:
- UI zeigt auswählbare Dataset-Karten.
- Ungültige Daten werden erklärt, nicht still ignoriert.

### 4. Training-Prozessmanager

Startbefehl:
`/opt/lichtfeld-dist/bin/run_lichtfeld.sh --headless --train -d <dataset> -o <output> -i <iterations> --strategy <strategy> --max-width <max_width> --log-level info`

Backend-Verhalten:
- Nur ein aktiver Trainingsjob gleichzeitig im MVP.
- PID wird gespeichert.
- stdout/stderr werden in Logdatei geschrieben.
- Status: idle, starting, running, stopping, exited, failed.
- Stop sendet erst SIGTERM, danach SIGKILL nach Timeout.

Akzeptanz:
- Start über WebUI erzeugt Output-Ordner unter `/workspace/output/<dataset>-YYYYmmdd-HHMMSS`.
- Logs erscheinen live in der UI.
- Stop beendet den Prozess nachvollziehbar.

### 5. Training-Monitoring

MVP-Datenquellen:
- Prozessstatus
- Log Parsing für Iteration/Loss, soweit LichtFeld diese Werte ausgibt
- GPU-Auslastung via nvidia-smi
- Output-Dateien im Output-Ordner

UI-Anzeige:
- Job-State
- Dataset
- Output-Pfad
- Iterationen geplant/erkannt
- letzter Loss, falls parsebar
- Laufzeit
- GPU Memory/Utilization/Temp
- Live-Log-Konsole

Akzeptanz:
- Auch wenn Loss nicht parsebar ist, bleibt UI stabil und zeigt Logs/GPU/Prozessstatus.

### 6. UI-Layout MVP

Screens:
- Dashboard
- Datasets
- Training
- Outputs/Exports
- Logs/Diagnostics

Komponenten:
- AppShell
- Sidebar
- TopStatusBar
- DatasetPicker
- TrainingConfigPanel
- JobStatusCard
- GpuCard
- LogViewer
- OutputBrowser
- CommandPreview

Design:
- dunkler Hintergrund, kompakte Panels
- Akzentfarbe zurückhaltend, z.B. cyan/blau
- monospace für Pfade/Commands/Logs
- Fokus auf technische Lesbarkeit
- responsive genug für 1366px bis 4K, primär Desktop/Tablet, kein Mobile-first-Zwang

Akzeptanz:
- Primärer Flow: Dataset wählen -> Parameter setzen -> Command prüfen -> Start -> Logs/GPU beobachten.

### 7. Output/Export-Browser

MVP:
- Listet `/workspace/output`.
- Zeigt Dateigröße, mtime, Dateityp.
- Download-Link für einzelne Dateien, sofern sinnvoll.
- Hinweise für PLY/SOG/SPZ/HTML-Viewer-Artefakte.

Später:
- Export über LichtFeld MCP/API, falls verfügbar.
- Vorschau für HTML-Viewer-Export.

### 8. Optional: COLMAP-Helfer

Nur implementieren, wenn gewünscht.

Funktion:
- Für loose-images Ordner COLMAP automatic_reconstructor starten.
- Separater Job-Typ `colmap`.
- Logs streamen.

Risiko:
- COLMAP ist aktuell nicht im Runtime-Image installiert.
- Erhöht Image-Größe.
- Lange Laufzeiten und Fehlerfälle.

Empfehlung:
- Nicht in MVP, außer du willst Bilder direkt ohne vorbereitete COLMAP-Struktur hochladen.

### 9. Optional: MCP-Integration

Upstream LichtFeld hat MCP/Runtime-Tools für:
- `scene.load_dataset`
- `training.start`
- `training.main`
- `scene.export_*`
- Runtime Events

Plan:
- Erst prüfen, ob MCP im headless/containerisierten Betrieb stabil verfügbar ist.
- Falls ja: Backend-Adapter `LichtfeldMcpClient` ergänzen.
- Falls nein: CLI-Prozessmanager bleibt primärer Weg.

Akzeptanz:
- Keine harte Abhängigkeit von MCP im MVP.
- Adapter-Schicht erlaubt späteren Wechsel ohne UI-Neubau.

## Implementierungsphasen

### Phase 0: Klärung und UI-Referenz sammeln

Tasks:
1. Desktop-GUI-Screenshots oder Referenzvideos sammeln.
2. Entscheiden, ob React/TypeScript oder statische UI.
3. Port/Auth/Scope entscheiden.
4. Dataset-Erwartung festlegen: COLMAP-only oder inkl. COLMAP-Generator.

Exit-Kriterium:
- Offene Fragen unten beantwortet.

### Phase 1: Backend-Skeleton

Tasks:
1. `webui/backend/requirements.txt` mit FastAPI/Uvicorn/Pydantic anlegen.
2. `app.py` mit Health/Version/Config-Endpunkten bauen.
3. Tests für Dataset-Erkennung schreiben.
4. Dataset-Scanner implementieren.
5. GPU-Parser implementieren.
6. Lokalen Backend-Start dokumentieren.

Verification:
- `python3 -m pytest webui/backend/tests -v`
- `uvicorn app:app --host 0.0.0.0 --port 7860`
- `curl localhost:7860/api/health`

### Phase 2: Training-Prozessmanager

Tasks:
1. Job-State-Modell definieren.
2. Command Builder mit sicherer Argumentliste implementieren, keine Shell-Interpolation.
3. Start/Stop-Endpunkte implementieren.
4. Logdatei-Streaming implementieren.
5. Status-Recovery bei Backend-Neustart minimal unterstützen.

Verification:
- Fake-LichtFeld-Script-Test für Start/Stop/Logs.
- Im Container: `POST /api/train/start` mit Testdataset.

### Phase 3: Frontend MVP

Tasks:
1. AppShell und Routing/Tabs bauen.
2. DatasetPicker an `/api/datasets` anbinden.
3. TrainingConfigPanel bauen.
4. CommandPreview aus Backend oder lokalem Command-Modell anzeigen.
5. Start/Stop-Buttons anbinden.
6. Live-Logs per SSE/WebSocket anzeigen.
7. GPU-Karte regelmäßig aktualisieren.

Verification:
- UI öffnet auf Port 7860.
- Start-Flow funktioniert in Browser.
- Keine Console Errors.

### Phase 4: Container-Integration

Tasks:
1. Dockerfile um WebUI-Abhängigkeiten erweitern.
2. Frontend-Build in Image integrieren.
3. `runpod-start.sh` um `start_lichtfeld_webui` erweitern.
4. Port 7860 exposen.
5. Env-Variablen dokumentieren.
6. GitHub Actions Build starten.

Verification:
- GitHub Actions Build success.
- RunPod Pod mit neuem Image startet FileBrowser, ttyd, SSH und WebUI.
- `/api/health` erreichbar.

### Phase 5: Polishing und Desktop-GUI-Anlehnung

Tasks:
1. Screenshots der Desktop-GUI analysieren.
2. Farb-/Spacing-/Panel-System angleichen.
3. Labels und Gruppierung an Desktop-Begriffe angleichen.
4. Leere Zustände und Fehlerzustände sauber gestalten.
5. Accessibility-Basics: Fokus, Kontrast, Keyboard-Bedienbarkeit.

Verification:
- UI-Screenshot gegen Desktop-Referenz vergleichen.
- Nutzerfeedback einarbeiten.

### Phase 6: Nice-to-have Erweiterungen

Optionen:
- COLMAP-Job aus loose images.
- MCP-basierte Steuerung statt CLI-Prozess.
- Training-Presets speichern.
- Mehrere Projekte/Szenen verwalten.
- Export-Buttons für PLY/SOG/SPZ/HTML.
- HTML-Viewer Preview einbetten.
- Auth für WebUI.
- RunPod Pod-Metadaten anzeigen.

## Risiken und Gegenmaßnahmen

1. Desktop-GUI ist nicht dokumentiert/sichtbar genug.
   - Gegenmaßnahme: Screenshots verlangen, MVP layoutnah aber nicht pixelgenau bauen.

2. LichtFeld-Logs enthalten keine stabil parsebaren Iterations-/Loss-Zeilen.
   - Gegenmaßnahme: UI zeigt Logs robust; Parsing optional und fehlertolerant.

3. MCP funktioniert nur mit laufender GUI/HTTP Bridge, nicht sauber headless.
   - Gegenmaßnahme: CLI-Prozessmanager als stabiler MVP.

4. WebUI ohne Auth ist auf RunPod-Proxy-URL grundsätzlich erreichbar.
   - Gegenmaßnahme: Auth optional oder standardmäßig Basic Auth, je nach Entscheidung.

5. Image wird größer durch Node/Frontend-Build/COLMAP.
   - Gegenmaßnahme: Multi-stage build; COLMAP nur optional.

6. Training-Prozess überlebt Backend-Neustart nicht vollständig beobachtbar.
   - Gegenmaßnahme: PID-/Logdatei-basierte Recovery im MVP, robustere Supervisor später.

## Offene Entscheidungen

Die nächsten Entscheidungen werden einzeln im Chat geklärt. Keine Sammelfragen mehr. Nach jeder Antwort wird der Plan bei Bedarf aktualisiert.


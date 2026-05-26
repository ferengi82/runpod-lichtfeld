# LichtFeld Studio Code-Analyse für RunPod WebUI

Stand: 2026-05-26
Upstream: https://github.com/MrNeRF/LichtFeld-Studio
Lokale Analyse-Kopie: /home/hermes/work/LichtFeld-Studio

## 1. Architektur / Technologie-Stack

LichtFeld Studio ist keine klassische Web-App, sondern eine native C++/Python-Anwendung mit GPU-Rendering.

Wichtige Bausteine:

- C++ Core unter `src/`
  - Scene/Rendering/Training/IO/GUI-Brücken
  - GPU-nahe Renderer, Splats, Meshes, Selektion, Viewport
- Python Plugin-System unter `src/python/lfs_plugins/`
  - Menüs, Panels und viele UI-Actions sind Python-Plugins
  - Import/Export/Training/Rendering sind hier gut nachvollziehbar
- RmlUI Templates unter `src/visualizer/gui/rmlui/resources/*.rml`
  - deklarative UI, ähnlich HTML
  - Buttons verwenden `data-event-click=...`
  - Datenbindung läuft über `data-model=...`
- Python-Bindings `lichtfeld` / `lf`
  - Panels rufen Funktionen wie `lf.start_training()`, `lf.load_file()`, `lf.export_scene()` auf
- RunPod WebUI in diesem Repo ist separat:
  - FastAPI Backend: `webui/backend/lichtfeld_webui/app.py`, `core.py`
  - statisches Frontend: `webui/static/index.html`

Konsequenz für unsere WebUI:

- Wir müssen die Desktop-GUI nicht 1:1 portieren.
- Sinnvoll ist eine WebUI, die dieselben Kernoperationen abbildet:
  - Dataset erkennen/importieren
  - Headless Training starten/stoppen
  - Output-Dateien erkennen
  - Output previewen/exportieren/downloaden
- Für echte Desktop-Viewport-Funktionen wie Splat-Selektion, Gizmos oder native Renderer brauchen wir später entweder Exportformate oder einen dedizierten Viewer.

## 2. Haupt-Menüs und Actions

Quelle: `src/python/lfs_plugins/file_menu.py`

File-Menü:

- New Project
  - Operator: `NewProjectOperator`
  - Aktion: `lf.new_project()`
- Import Dataset
  - Operator: `ImportDatasetOperator`
  - Dialog: `lf.ui.open_dataset_folder_dialog()`
  - öffnet Dataset-Import-Panel
- Import PLY
  - Operator: `ImportPlyOperator`
  - Dialog: `lf.ui.open_ply_file_dialog("")`
  - lädt Datei: `lf.load_file(path, is_dataset=False)`
- Import Mesh
  - Operator: `ImportMeshOperator`
  - Dialog: `lf.ui.open_mesh_file_dialog("")`
  - lädt Datei: `lf.load_file(path, is_dataset=False)`
- Import Checkpoint
  - Operator: `ImportCheckpointOperator`
  - Dialog: `lf.ui.open_checkpoint_file_dialog()`
  - öffnet Resume-Checkpoint-Panel
- Import Config
  - Operator: `ImportConfigOperator`
  - Dialog: `lf.ui.open_json_file_dialog()`
  - lädt Config: `lf.load_config_file(path)`
- Export
  - Operator: `ExportOperator`
  - öffnet Panel: `lf.ui.set_panel_enabled("lfs.export", True)`
- Export Config
  - Operator: `ExportConfigOperator`
  - Dialog: `lf.ui.save_json_file_dialog("config.json")`
  - speichert Config: `lf.save_config_file(path)`
- Mesh to Splat
  - Operator: `Mesh2SplatOperator`
  - öffnet Panel: `lf.ui.set_panel_enabled("native.mesh2splat", True)`
- Extract Video Frames
  - Operator: `ExtractVideoFramesOperator`
  - öffnet Panel: `lf.ui.set_panel_enabled("native.video_extractor", True)`
- Exit
  - Operator: `ExitOperator`
  - Confirm-Dialog, danach `lf.force_exit()`

Tools-Menü:

- Asset Manager
  - `lf.ui.set_panel_enabled("lfs.asset_manager", True)`
- URL Import
  - `lf.ui.set_panel_enabled("lfs.url_import", True)`

Edit/View:

- Edit enthält Undo/Redo und Panel-/Tool-Actions.
- View setzt Theme und UI Scale.

## 3. Import Panels

Quelle: `src/python/lfs_plugins/import_panels.py`
Templates:

- `dataset_import_panel.rml`
- `resume_checkpoint_panel.rml`
- `url_import_panel.rml`
- `watch_dirs_dialog.rml`

Dataset Import (`DatasetImportPanel`):

Buttons / Events:

- `browse_dataset`
  - öffnet Dataset-Folder-Dialog
- `browse_output`
  - öffnet Output-Folder-Dialog
- `browse_init`
  - öffnet PLY-Dialog für Initialisierungspunktwolke
- `browse_ppisp_sidecar`
  - öffnet PPISP-Dateidialog
- `do_load`
  - validiert Pfade
  - ruft `lf.load_file(dataset_path, ...)`
  - setzt Output-Pfad/Optimierungsparameter
- `do_cancel`
  - schließt Panel

Resume Checkpoint (`ResumeCheckpointPanel`):

- `browse_dataset`
- `browse_output`
- `do_load`
  - validiert Dataset
  - ruft `lf.load_checkpoint_for_training(...)`
- `do_cancel`

Für unsere WebUI relevant:

- `/api/datasets` sollte COLMAP-Datasets erkennen: `images/` plus `sparse/0/cameras.*` und `images.*`.
- Training braucht mindestens `dataset_path`, `output_path`, Strategie, Iterationen, Breite/Resize.
- Checkpoint-Resume wäre ein späterer eigener API-Endpunkt.

## 4. Training Panel

Quelle: `src/python/lfs_plugins/training_panel.py`
Template: `training.rml`
Panel-ID: `lfs.training`

Zentrale Actions:

- `action('start')`
  - Python: `_action_start()`
  - validiert Optimierungsparameter
  - ggf. Konflikt-Dialog bei Strategy/GUT
  - ggf. Speichern modifizierter Pointcloud anbieten
  - danach `lf.start_training()`
- `action('pause')`
  - `lf.pause_training()`
- `action('resume')`
  - `lf.resume_training()`
- `action('stop')`
  - `lf.stop_training()`
- `action('reset')`
  - `lf.reset_training()`
- `action('clear')`
  - `lf.new_project()`
- `action('switch_edit')`
  - `lf.switch_to_edit_mode()`
- `action('save_checkpoint')`
  - `lf.save_checkpoint()`
- `action('browse_bg')`
  - `lf.ui.open_image_dialog("")`, setzt `params.bg_image_path`
- `action('clear_bg')`
  - leert `params.bg_image_path`
- `action('browse_ppisp_sidecar')`
  - `lf.ui.open_ppisp_file_dialog(...)`, setzt PPISP Parameter
- `action('clear_ppisp_sidecar')`
  - leert PPISP Sidecar
- `action('add_step')`
  - fügt Save-Step hinzu
- `remove_step(it_index)`
  - entfernt Save-Step
- `num_step('<param>', +/-1)`
  - inkrementiert/dekrementiert numerische Parameter
- `toggle_section(...)`
  - klappt UI-Abschnitte ein/aus
- `color_click('bg_color')` / `picker_change`
  - Background-Color Picker

Wichtige Parametergruppen:

- Basic:
  - `strategy`: mcmc, mrnf/mnrf/lfs, igs+
  - `iterations`
  - `max_cap`
  - `sh_degree`
  - `tile_mode`
  - `steps_scaler`
  - `bilateral_grid`, `mask_mode`, `bg_mode`, `gut`, `undistort`, `mip_filter`, `ppisp`
- Dataset:
  - `dataset_path`, `image_count`, `resize_factor`, `max_width`, CPU/FS Cache, Eval/Test Every, Output
- Optimization:
  - Learning Rates für Position/SH/Opacity/Scale/Rotation
  - Refinement: `refine_every`, `start_refine`, `stop_refine`, `grad_threshold`, `reset_every`, `sh_degree_interval`
- Losses:
  - `lambda_dssim`, `opacity_reg`, `scale_reg`, `tv_loss_weight`
- Initialization:
  - `init_opacity`, `init_scaling`, `random`, `init_num_pts`, `init_extent`
- Save/Eval Steps:
  - Save-Checkpoint-Steps und optionale Eval-Steps

Für unsere WebUI relevant:

- Aktuell bildet `webui/backend/lichtfeld_webui/core.py` den minimalen Headless-Befehl schon passend ab:
  - `run_lichtfeld.sh --headless --train -d DATASET -o OUTPUT -i ITER --strategy STRATEGY --max-width WIDTH --log-level info`
  - optional `--resize_factor`, `--gut`
- Nächste sinnvolle Erweiterungen:
  - Pause/Resume/Reset nur implementieren, wenn Headless CLI dafür Signale/API unterstützt. Sonst Stop + neuer Lauf.
  - Save-Checkpoint/Resume später über Checkpoint-Dateien in `/workspace/output`.
  - Fortschritt aus Logs parsen: Iteration, Loss, PSNR, Save-Events.

## 5. Export Panel

Quelle: `src/python/lfs_plugins/export_panel.py`
Template: `export_panel.rml`
Panel-ID: `lfs.export`

Exportformate:

- `PLY` – Standard Splat/Pointcloud Format
- `SOG` – SuperSplat
- `SPZ` – Niantic
- `HTML_VIEWER` – eigenständiger HTML Viewer
- `USD`
- `NUREC_USDZ`
- `RAD` – Random Access
- `COLMAP` – Sparse COLMAP Export

Zentrale Events:

- Format-Auswahl
  - aktualisiert Format-Records und Sichtbarkeit
- Model-Auswahl
  - wählt einzelne Splat Nodes
- `do_export`
  - prüft Auswahl/Pfad
  - Save-Dialog je Format:
    - `lf.ui.save_ply_file_dialog`
    - `lf.ui.save_sog_file_dialog`
    - `lf.ui.save_spz_file_dialog`
    - `lf.ui.save_usd_file_dialog`
    - `lf.ui.save_usdz_file_dialog`
    - `lf.ui.save_html_file_dialog`
    - `lf.ui.save_rad_file_dialog`
    - `lf.ui.select_colmap_sparse_folder_dialog`
  - startet `lf.export_scene(...)`
- `do_cancel_export`
  - `lf.ui.cancel_export()`
- `do_cancel`
  - schließt Panel
- RAD-spezifisch:
  - `toggle_rad_flip_y`
  - `toggle_rad_customize_lod`
  - `add_rad_lod`, `remove_rad_lod`, `num_step_rad_lod`, `update_lod_value`

Für unsere WebUI relevant:

- `/api/outputs` sollte nicht nur Dateien auflisten, sondern Preview-Kandidaten klassifizieren.
- Priorität für Browser-Preview:
  1. `.ply` als Pointcloud/Splat-Basis
  2. `.sog`, `.spz` erkennen und Download/externen Hinweis anbieten
  3. `HTML_VIEWER` direkt einbetten/verlinken
  4. `.usd/.usdz/.rad` zunächst als Export/Download anzeigen
  5. COLMAP sparse (`cameras.bin/txt`, `images.bin/txt`, `points3D.bin/txt`) später als Kamera-/Punktwolken-Preview

## 6. Rendering Panel

Quelle: `src/python/lfs_plugins/rendering_panel.py`
Template: `rendering.rml`
Panel-ID: Rendering

Wichtige UI-Bereiche:

- Viewport/Camera:
  - Projection, Raster Backend, Environment Mode/Map, Background Color
- Simplify:
  - Splat-Vereinfachung
  - `simplify_apply()` ruft intern `lf.simplify_splats(...)`
  - `simplify_cancel()` bricht Task ab
- Selection/Overlays:
  - Farben und Anzeigeoptionen für Auswahl/Cropping/Depth Box
- Mesh:
  - Wireframe, Farbe, Licht, Ambient, Backface Culling, Shadows
- Post Processing:
  - Vignette, Appearance Correction / PPISP, Gamma/CRF
- Windows:
  - `toggle_console`

Für unsere WebUI relevant:

- Rendering-Einstellungen sind für den ersten Web-Preview nur teilweise wichtig.
- Sinnvoll für Version 1:
  - Background-Farbe
  - Grid/Achsen
  - Point size / Splat size
  - Auto-Fit Kamera
- Später:
  - Mesh wireframe/material toggles
  - Color management/Exposure
  - Crop/Selection Overlays

## 7. Mesh2Splat Panel

Quelle: `src/python/lfs_plugins/mesh2splat_panel.py`
Template: `mesh2splat_panel.rml`
Panel-ID: `native.mesh2splat`

Events:

- Mesh-Liste auswählbar
- Auflösung auswählbar
- `do_convert`
  - prüft `lf.is_mesh2splat_active()`
  - startet `lf.mesh_to_splat(...)`
  - Fortschritt über `lf.get_mesh2splat_progress()`
  - Fehler über `lf.get_mesh2splat_error()`

Für unsere WebUI relevant:

- Erst nach der generischen Preview sinnvoll.
- Mesh-Dateien (`.obj`, `.glb`, `.gltf`) können wir direkt im Browser mit Three.js anzeigen.
- Mesh->Splat-Konvertierung sollte später als API-Job ergänzt werden, wenn CLI/API klar ist.

## 8. Viewport Overlay / Toolbar

Quelle: `viewport_overlay.rml` plus Plugins `toolbar.py`, `selection_controls.py`, `transform_controls.py`

Events:

- `toolbar_action(button.action, button.value)`
- `selection_action('select_all'|'unselect'|'invert'|'delete'|'undo'|'redo'|'toggle_depth')`
- `transform_action('bake'|'reset')`
- `transform_num_step('pos_x'...)`, Rotation, Scale
- `overlay_action('cancel_video_export'|'dismiss_import')`

Für unsere WebUI relevant:

- Für eine Output-Preview brauchen wir anfangs nur Viewport-Navigation:
  - Orbit/Pan/Zoom
  - Reset View
  - Fit to Object
- Desktop-spezifische Auswahl und Transform-Gizmos später.

## 9. Konkrete Umsetzungsempfehlung für RunPod WebUI

### Phase 1: robuste Output-Preview

Backend:

- `OutputFile` erweitern:
  - `previewable: bool`
  - `preview_type: pointcloud | mesh | html | colmap | unsupported`
  - `url: /api/outputs/file?...`
- sicheren Datei-Endpunkt ergänzen:
  - keine beliebigen absoluten Pfade ausliefern
  - nur Dateien unter `OUTPUT_ROOT`
- `list_outputs()` erweitert um Formate:
  - Pointcloud/Splat: `.ply`
  - Mesh: `.obj`, `.glb`, `.gltf`
  - HTML Viewer: `.html`
  - Erkennen/anzeigen: `.sog`, `.spz`, `.usd`, `.usdz`, `.rad`, COLMAP sparse

Frontend:

- rechten Bereich oder Viewport um Preview-Modus erweitern
- Three.js via CDN oder lokal vendored nutzen
- Loader:
  - `PLYLoader` für `.ply`
  - `OBJLoader` für `.obj`
  - `GLTFLoader` für `.glb/.gltf`
- UI:
  - Output-Liste
  - Datei auswählen
  - Preview laden
  - Download-Link
  - Reset/Fit View

### Phase 2: Training-Integration

- nach Trainingsende `/api/outputs` refreshen
- automatisch neuesten previewbaren Output laden
- Log-Parser für Iteration/Loss/PSNR
- Statuskarte analog Desktop Training Panel

### Phase 3: Export/Checkpoint/Resume

- Checkpoints erkennen
- Resume API ergänzen
- Exportformate explizit anzeigen
- HTML Viewer einbetten
- optional COLMAP-Kameras und Punkte anzeigen

## 10. Wichtigste Erkenntnis

Die Desktop-GUI ist im Kern ein RmlUI/Python-Plugin-Layer um `lf.*` Kernfunktionen. Für die RunPod-WebUI sollten wir nicht versuchen, diesen Layer direkt zu portieren. Besser ist:

- Dieselben Kern-Workflows nachbauen.
- Zuerst Preview und Trainingssteuerung stabil machen.
- Desktop-Buttons als Funktionsreferenz verwenden.
- Browser-Preview auf exportierten Dateien in `/workspace/output` aufbauen.

Damit bleibt die WebUI wartbar und funktioniert im headless RunPod-Kontext zuverlässig.

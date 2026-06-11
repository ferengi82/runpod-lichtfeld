
import tempfile
import unittest
from pathlib import Path

from lichtfeld_webui.core import (
    auto_steps_scaler,
    build_train_command,
    effective_iterations,
    list_outputs,
    parse_nvidia_smi_csv,
    resolve_output_path,
    scan_datasets,
)


class CoreTests(unittest.TestCase):
    def test_scan_datasets_detects_colmap_project(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            scene = root / "garden"
            (scene / "images").mkdir(parents=True)
            (scene / "images" / "001.jpg").write_bytes(b"jpg")
            (scene / "images" / "002.png").write_bytes(b"png")
            sparse = scene / "sparse" / "0"
            sparse.mkdir(parents=True)
            (sparse / "cameras.bin").write_bytes(b"cam")
            (sparse / "images.bin").write_bytes(b"img")
            (sparse / "points3D.bin").write_bytes(b"pts")

            datasets = scan_datasets(root)

        self.assertEqual(len(datasets), 1)
        ds = datasets[0]
        self.assertEqual(ds.name, "garden")
        self.assertEqual(ds.type, "colmap")
        self.assertEqual(ds.image_count, 2)
        self.assertTrue(ds.has_sparse)
        self.assertTrue(ds.ready)

    def test_scan_datasets_marks_loose_images_as_not_ready(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            scene = root / "loose"
            scene.mkdir()
            (scene / "a.jpg").write_bytes(b"jpg")

            datasets = scan_datasets(root)

        self.assertEqual(datasets[0].type, "loose_images")
        self.assertFalse(datasets[0].ready)
        self.assertIn("COLMAP", datasets[0].warnings[0])

    def test_build_train_command_uses_argument_list_without_shell_interpolation(self):
        cmd = build_train_command(
            lichtfeld_bin="/opt/lichtfeld-dist/bin/run_lichtfeld.sh",
            dataset_path="/workspace/data/garden",
            output_path="/workspace/output/run 1",
            iterations=7000,
            strategy="mcmc",
            max_width=3840,
            resize_factor="auto",
            gut=False,
        )

        self.assertEqual(cmd[0], "/opt/lichtfeld-dist/bin/run_lichtfeld.sh")
        self.assertIn("--headless", cmd)
        self.assertIn("--train", cmd)
        self.assertIn("/workspace/output/run 1", cmd)
        self.assertNotIn("--resize_factor", cmd)


    def test_auto_steps_scaler_matches_desktop_formula(self):
        self.assertEqual(auto_steps_scaler(0), 1.0)
        self.assertEqual(auto_steps_scaler(300), 1.0)
        self.assertAlmostEqual(auto_steps_scaler(450), 1.5)
        self.assertAlmostEqual(auto_steps_scaler(600), 2.0)

    def test_effective_iterations_scales_like_desktop_steps(self):
        self.assertEqual(effective_iterations(30000, 300), 30000)
        self.assertEqual(effective_iterations(30000, 450), 45000)
        self.assertEqual(effective_iterations(30000, 333), 33300)

    def test_build_train_command_can_pass_desktop_steps_scaler_without_shell_interpolation(self):
        cmd = build_train_command(
            lichtfeld_bin='/opt/lichtfeld-dist/bin/run_lichtfeld.sh',
            dataset_path='/workspace/data/big-scene',
            output_path='/workspace/output/big-scene',
            iterations=30000,
            strategy='mrnf',
            max_width=3840,
            steps_scaler=2.0,
        )

        self.assertIn('--steps-scaler', cmd)
        self.assertEqual(cmd[cmd.index('--steps-scaler') + 1], '2')
        self.assertEqual(cmd[cmd.index('-i') + 1], '30000')

    def test_parse_nvidia_smi_csv(self):
        rows = "NVIDIA GeForce RTX 4080, 17, 2730, 17190, 8, 47\n"

        gpus = parse_nvidia_smi_csv(rows)

        self.assertEqual(gpus, [
            {
                "name": "NVIDIA GeForce RTX 4080",
                "memory_used_mb": 2730,
                "memory_total_mb": 17190,
                "utilization_gpu_percent": 8,
                "temperature_c": 47,
            }
        ])

    def test_list_outputs_marks_browser_previewable_formats(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "cloud.ply").write_bytes(b"ply")
            (root / "mesh.glb").write_bytes(b"glb")
            (root / "viewer.html").write_text("<html></html>")
            (root / "scene.spz").write_bytes(b"spz")

            outputs = {item.name: item.to_dict() for item in list_outputs(root)}

        self.assertTrue(outputs["cloud.ply"]["previewable"])
        self.assertEqual(outputs["cloud.ply"]["preview_type"], "pointcloud")
        self.assertTrue(outputs["mesh.glb"]["previewable"])
        self.assertEqual(outputs["mesh.glb"]["preview_type"], "mesh")
        self.assertTrue(outputs["viewer.html"]["previewable"])
        self.assertEqual(outputs["viewer.html"]["preview_type"], "html")
        self.assertFalse(outputs["scene.spz"]["previewable"])
        self.assertEqual(outputs["scene.spz"]["preview_type"], "download")

    def test_resolve_output_path_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "safe.ply").write_bytes(b"ply")
            safe = resolve_output_path(root, "safe.ply")
            unsafe = resolve_output_path(root, "../secret.txt")

        self.assertEqual(safe.name, "safe.ply")
        self.assertIsNone(unsafe)

    def test_webui_preview_auto_loads_visible_pointclouds(self):
        html = Path(__file__).resolve().parents[2] / "static" / "index.html"
        content = html.read_text()

        self.assertIn("currentPreviewName", content)
        self.assertIn("newest.name!==currentPreviewName", content)
        self.assertIn("function outputMatchesSelectedDataset(file)", content)
        self.assertIn("files.filter(outputMatchesSelectedDataset)", content)
        self.assertIn("refreshOutputs();", content)
        self.assertIn("loadPreview(newest);", content)
        self.assertIn("sizeAttenuation:false", content)
        self.assertNotIn("PointsMaterial({size:0.01", content)

    def test_webui_preview_applies_lichtfeld_y_axis_correction(self):
        html = Path(__file__).resolve().parents[2] / "static" / "index.html"
        content = html.read_text()

        self.assertIn("function applyLichtfeldPreviewTransform(obj)", content)
        self.assertIn("obj.scale.y *= -1", content)
        self.assertIn("applyLichtfeldPreviewTransform(obj);", content)

    def test_webui_preview_uses_gaussian_splat_renderer_for_ply_outputs(self):
        html = Path(__file__).resolve().parents[2] / "static" / "index.html"
        content = html.read_text()

        self.assertIn("@mkkellogg/gaussian-splats-3d", content)
        self.assertIn("function canRenderAsGaussianSplat(file)", content)
        self.assertIn("new GaussianSplats3D.Viewer", content)
        self.assertIn("GaussianSplats3D.SceneFormat.Ply", content)
        self.assertIn("scale:[1,1,1]", content)
        self.assertIn("function lichtfeldViewDirection()", content)
        self.assertIn("new THREE.Vector3(0.55,-0.42,1).normalize()", content)
        self.assertIn("function fitGaussianSplatPreview(attempt=0)", content)
        self.assertIn("getSplatTree", content)
        self.assertIn("mesh.boundingBox", content)
        self.assertIn("mesh.calculatedSceneCenter", content)
        self.assertIn("function scheduleGaussianSplatFit()", content)
        self.assertIn("splatViewer.controls?.target?.copy(center)", content)
        self.assertIn("scheduleGaussianSplatFit(); splatViewer.start();", content)
        self.assertIn("Pointcloud-Fallback", content)


    def test_webui_axis_widget_follows_active_camera(self):
        html = Path(__file__).resolve().parents[2] / "static" / "index.html"
        content = html.read_text()

        self.assertIn('id="axis-canvas"', content)
        self.assertIn("const axisRoot = new THREE.Group()", content)
        self.assertIn("function activePreviewCamera()", content)
        self.assertIn("return splatViewer?.camera || camera3d", content)
        self.assertIn("function updateAxisWidget()", content)
        self.assertIn("axisRoot.quaternion.copy(cam.quaternion).invert()", content)
        self.assertIn("axisRoot.scale.y=-1", content)
        self.assertIn("y:new THREE.Vector3(0,-1.22,0)", content)
        self.assertIn("updateAxisWidget();", content)


    def test_webui_dataset_change_refreshes_matching_outputs_across_script_scopes(self):
        html = Path(__file__).resolve().parents[2] / "static" / "index.html"
        content = html.read_text()

        self.assertIn("window.refreshOutputs?.();", content)
        self.assertIn("window.refreshOutputs=refreshOutputs", content)
        self.assertIn("window.resetPreviewStateForDataset?.();", content)
        self.assertIn("function selectedDatasetName()", content)
        self.assertIn("function outputMatchesSelectedDataset(file)", content)

    def test_webui_auto_iterations_from_dataset_image_count(self):
        html = Path(__file__).resolve().parents[2] / 'static' / 'index.html'
        content = html.read_text()

        self.assertIn('id="steps-scaler"', content)
        self.assertIn('id="effective-iterations"', content)
        self.assertIn('const BASE_ITERATIONS=30000', content)
        self.assertIn('function autoStepsScaler(imageCount)', content)
        self.assertIn('Math.max(1, imageCount/300)', content)
        self.assertIn('function applyAutoIterationsForDataset()', content)
        self.assertIn('steps_scaler:autoStepsScaler(d.image_count)', content)
        self.assertIn('--steps-scaler', content)

    def test_webui_defaults_strategy_to_mrnf(self):
        html = Path(__file__).resolve().parents[2] / "static" / "index.html"
        content = html.read_text()

        self.assertIn('<option selected>mrnf</option>', content)


if __name__ == "__main__":
    unittest.main()


import tempfile
import unittest
from pathlib import Path

from lichtfeld_webui.core import (
    build_train_command,
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


if __name__ == "__main__":
    unittest.main()

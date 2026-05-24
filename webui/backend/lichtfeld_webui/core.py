
from __future__ import annotations

import csv
import os
import signal
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Lock
from typing import Iterable, Literal

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}
VALID_STRATEGIES = {"mcmc", "mrnf", "igs+", "mnrf", "lfs"}


@dataclass(slots=True)
class DatasetInfo:
    name: str
    path: str
    type: Literal["colmap", "loose_images", "unknown"]
    image_count: int
    has_sparse: bool
    ready: bool
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class OutputFile:
    name: str
    path: str
    size_bytes: int
    modified_time: float
    kind: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class TrainingJob:
    id: str
    status: str
    dataset_path: str | None = None
    output_path: str | None = None
    log_path: str | None = None
    command: list[str] = field(default_factory=list)
    pid: int | None = None
    started_at: float | None = None
    ended_at: float | None = None
    returncode: int | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        if self.started_at:
            data["runtime_seconds"] = round((self.ended_at or time.time()) - self.started_at, 1)
        else:
            data["runtime_seconds"] = 0
        return data


def count_images(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return 1 if path.suffix.lower() in IMAGE_EXTENSIONS else 0
    return sum(1 for p in path.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS)


def has_colmap_sparse(path: Path) -> bool:
    sparse = path / "sparse" / "0"
    return sparse.is_dir() and any((sparse / f"cameras{ext}").exists() for ext in (".bin", ".txt")) and any(
        (sparse / f"images{ext}").exists() for ext in (".bin", ".txt")
    )


def classify_dataset(path: Path) -> DatasetInfo:
    images_dir = path / "images"
    direct_image_count = sum(1 for child in path.iterdir() if child.is_file() and child.suffix.lower() in IMAGE_EXTENSIONS) if path.is_dir() else 0
    image_count = count_images(images_dir) if images_dir.is_dir() else direct_image_count
    has_sparse = has_colmap_sparse(path)
    warnings: list[str] = []

    if images_dir.is_dir() and has_sparse:
        dtype: Literal["colmap", "loose_images", "unknown"] = "colmap"
        ready = True
    elif image_count > 0:
        dtype = "loose_images"
        ready = False
        warnings.append("Bilder gefunden, aber keine COLMAP-Struktur sparse/0 mit cameras/images metadata.")
    else:
        dtype = "unknown"
        ready = False
        warnings.append("Kein COLMAP-Dataset und keine Bilder erkannt.")

    return DatasetInfo(
        name=path.name,
        path=str(path),
        type=dtype,
        image_count=image_count,
        has_sparse=has_sparse,
        ready=ready,
        warnings=warnings,
    )


def scan_datasets(root: str | Path) -> list[DatasetInfo]:
    root = Path(root)
    if not root.exists():
        return []

    candidates: list[Path] = []
    root_info = classify_dataset(root)
    if root_info.type != "unknown":
        candidates.append(root)
    else:
        candidates.extend(p for p in sorted(root.iterdir()) if p.is_dir())

    datasets = [classify_dataset(p) for p in candidates]
    return [d for d in datasets if d.type != "unknown" or d.image_count > 0]


def build_train_command(
    *,
    lichtfeld_bin: str,
    dataset_path: str,
    output_path: str,
    iterations: int,
    strategy: str,
    max_width: int,
    resize_factor: str = "auto",
    gut: bool = False,
) -> list[str]:
    if strategy not in VALID_STRATEGIES:
        raise ValueError(f"Unsupported strategy: {strategy}")
    if iterations <= 0:
        raise ValueError("iterations must be greater than 0")
    if max_width < 0:
        raise ValueError("max_width must be >= 0")

    cmd = [
        lichtfeld_bin,
        "--headless",
        "--train",
        "-d",
        dataset_path,
        "-o",
        output_path,
        "-i",
        str(iterations),
        "--strategy",
        strategy,
        "--max-width",
        str(max_width),
        "--log-level",
        "info",
    ]
    if resize_factor != "auto":
        cmd.extend(["--resize_factor", resize_factor])
    if gut:
        cmd.append("--gut")
    return cmd


def parse_nvidia_smi_csv(text: str) -> list[dict]:
    gpus: list[dict] = []
    for row in csv.reader(line for line in text.splitlines() if line.strip()):
        if len(row) < 6:
            continue
        name = row[0].strip()
        # row[1] is index in the query used by get_gpu_info; kept for compatibility.
        try:
            gpus.append(
                {
                    "name": name,
                    "memory_used_mb": int(float(row[2].strip())),
                    "memory_total_mb": int(float(row[3].strip())),
                    "utilization_gpu_percent": int(float(row[4].strip())),
                    "temperature_c": int(float(row[5].strip())),
                }
            )
        except ValueError:
            continue
    return gpus


def get_gpu_info() -> list[dict]:
    query = "name,index,memory.used,memory.total,utilization.gpu,temperature.gpu"
    try:
        proc = subprocess.run(
            ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    return parse_nvidia_smi_csv(proc.stdout)


def list_outputs(root: str | Path, limit: int = 200) -> list[OutputFile]:
    root = Path(root)
    if not root.exists():
        return []
    files: list[OutputFile] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        ext = p.suffix.lower().lstrip(".") or "file"
        files.append(OutputFile(p.name, str(p), st.st_size, st.st_mtime, ext))
    files.sort(key=lambda item: item.modified_time, reverse=True)
    return files[:limit]


class TrainingManager:
    def __init__(self, workspace: Path, lichtfeld_bin: str):
        self.workspace = workspace
        self.lichtfeld_bin = lichtfeld_bin
        self.log_dir = workspace / "logs"
        self.output_root = workspace / "output"
        self._lock = Lock()
        self._job = TrainingJob(id="current", status="idle")
        self._process: subprocess.Popen | None = None

    def current_job(self) -> TrainingJob:
        with self._lock:
            self._refresh_locked()
            return self._job

    def start(
        self,
        *,
        dataset_path: str,
        output_name: str | None,
        iterations: int,
        strategy: str,
        max_width: int,
        resize_factor: str = "auto",
        gut: bool = False,
    ) -> TrainingJob:
        with self._lock:
            self._refresh_locked()
            if self._process and self._process.poll() is None:
                raise RuntimeError("A training job is already running")

            safe_name = output_name or f"{Path(dataset_path).name}-{time.strftime('%Y%m%d-%H%M%S')}"
            safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in safe_name).strip("-") or "lichtfeld-run"
            output_path = self.output_root / safe_name
            output_path.mkdir(parents=True, exist_ok=True)
            self.log_dir.mkdir(parents=True, exist_ok=True)
            log_path = self.log_dir / f"lichtfeld-train-{safe_name}.log"
            cmd = build_train_command(
                lichtfeld_bin=self.lichtfeld_bin,
                dataset_path=dataset_path,
                output_path=str(output_path),
                iterations=iterations,
                strategy=strategy,
                max_width=max_width,
                resize_factor=resize_factor,
                gut=gut,
            )
            log_file = log_path.open("ab", buffering=0)
            log_file.write(("\n===== LichtFeld training started %s =====\n" % time.strftime("%Y-%m-%dT%H:%M:%S%z")).encode())
            log_file.write(("Command: " + " ".join(cmd) + "\n").encode())
            proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT, cwd=str(self.workspace), start_new_session=True)
            self._process = proc
            self._job = TrainingJob(
                id="current",
                status="running",
                dataset_path=dataset_path,
                output_path=str(output_path),
                log_path=str(log_path),
                command=cmd,
                pid=proc.pid,
                started_at=time.time(),
            )
            return self._job

    def stop(self) -> TrainingJob:
        with self._lock:
            self._refresh_locked()
            if not self._process or self._process.poll() is not None:
                self._job.status = "idle" if self._job.status in {"idle", "exited"} else self._job.status
                return self._job
            self._job.status = "stopping"
            try:
                os.killpg(self._process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            return self._job

    def _refresh_locked(self) -> None:
        if not self._process:
            return
        rc = self._process.poll()
        if rc is None:
            return
        if self._job.ended_at is None:
            self._job.returncode = rc
            self._job.ended_at = time.time()
            self._job.status = "exited" if rc == 0 else "failed"


def tail_file(path: str | Path, max_bytes: int = 65536) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    size = p.stat().st_size
    with p.open("rb") as f:
        if size > max_bytes:
            f.seek(size - max_bytes)
        data = f.read()
    return data.decode("utf-8", errors="replace")

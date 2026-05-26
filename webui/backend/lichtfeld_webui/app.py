
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .core import TrainingManager, get_gpu_info, list_outputs, resolve_output_path, scan_datasets, tail_file

WORKSPACE = Path(os.environ.get('RUNPOD_WORKSPACE', '/workspace'))
DATA_ROOT = Path(os.environ.get('LICHTFELD_WEBUI_DATA_ROOT', str(WORKSPACE / 'data')))
OUTPUT_ROOT = Path(os.environ.get('LICHTFELD_WEBUI_OUTPUT_ROOT', str(WORKSPACE / 'output')))
LICHTFELD_BIN = os.environ.get('LICHTFELD_BIN', '/opt/lichtfeld-dist/bin/run_lichtfeld.sh')
STATIC_DIR = Path(__file__).resolve().parents[2] / 'static'

app = FastAPI(title='LichtFeld Studio WebUI', version='0.1.0')
manager = TrainingManager(WORKSPACE, LICHTFELD_BIN)


class TrainStartRequest(BaseModel):
    dataset_path: str
    output_name: str | None = None
    iterations: int = Field(default=7000, ge=1, le=1_000_000)
    strategy: str = 'mcmc'
    max_width: int = Field(default=3840, ge=0, le=65535)
    resize_factor: str = 'auto'
    gut: bool = False


@app.get('/api/health')
def health() -> dict[str, Any]:
    return {
        'ok': True,
        'service': 'lichtfeld-webui',
        'version': app.version,
        'workspace': str(WORKSPACE),
        'data_root': str(DATA_ROOT),
        'output_root': str(OUTPUT_ROOT),
        'lichtfeld_bin': LICHTFELD_BIN,
        'lichtfeld_bin_exists': Path(LICHTFELD_BIN).exists(),
    }


@app.get('/api/version')
def version() -> dict[str, Any]:
    revision_path = Path('/opt/lichtfeld-upstream-revision.txt')
    return {
        'webui': app.version,
        'lichtfeld_revision': revision_path.read_text().strip() if revision_path.exists() else 'unknown',
    }


@app.get('/api/config')
def config() -> dict[str, Any]:
    return {
        'workspace': str(WORKSPACE),
        'data_root': str(DATA_ROOT),
        'output_root': str(OUTPUT_ROOT),
        'default_iterations': 7000,
        'strategies': ['mcmc', 'mrnf', 'igs+'],
        'resize_factors': ['auto', '1', '2', '4', '8'],
    }


@app.get('/api/gpu')
def gpu() -> dict[str, Any]:
    return {'gpus': get_gpu_info()}


@app.get('/api/datasets')
def datasets() -> dict[str, Any]:
    return {'datasets': [d.to_dict() for d in scan_datasets(DATA_ROOT)]}


@app.get('/api/outputs')
def outputs() -> dict[str, Any]:
    return {'files': [f.to_dict() for f in list_outputs(OUTPUT_ROOT)]}


@app.get('/api/outputs/file')
def output_file(path: str):
    resolved = resolve_output_path(OUTPUT_ROOT, path)
    if resolved is None:
        raise HTTPException(status_code=404, detail='output file not found')
    return FileResponse(resolved)


@app.get('/api/jobs/current')
def current_job() -> dict[str, Any]:
    return manager.current_job().to_dict()


@app.post('/api/train/start')
def train_start(req: TrainStartRequest) -> dict[str, Any]:
    dataset = Path(req.dataset_path)
    try:
        dataset.resolve().relative_to(DATA_ROOT.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail='dataset_path must be under the configured data root') from exc
    if not dataset.exists():
        raise HTTPException(status_code=404, detail='dataset_path does not exist')
    try:
        job = manager.start(
            dataset_path=str(dataset),
            output_name=req.output_name,
            iterations=req.iterations,
            strategy=req.strategy,
            max_width=req.max_width,
            resize_factor=req.resize_factor,
            gut=req.gut,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return job.to_dict()


@app.post('/api/train/stop')
def train_stop() -> dict[str, Any]:
    return manager.stop().to_dict()


@app.get('/api/logs/current')
def current_log() -> dict[str, Any]:
    job = manager.current_job()
    return {'log': tail_file(job.log_path) if job.log_path else ''}


@app.get('/api/logs/current/stream')
async def stream_current_log():
    async def events():
        last_text = None
        while True:
            job = manager.current_job()
            text = tail_file(job.log_path) if job.log_path else ''
            payload = {'job': job.to_dict(), 'log': text}
            encoded = json.dumps(payload)
            if encoded != last_text:
                yield f'data: {encoded}\n\n'
                last_text = encoded
            await asyncio.sleep(1.5)
    return StreamingResponse(events(), media_type='text/event-stream')


@app.get('/')
def index():
    return FileResponse(STATIC_DIR / 'index.html')


if STATIC_DIR.exists():
    app.mount('/static', StaticFiles(directory=str(STATIC_DIR)), name='static')

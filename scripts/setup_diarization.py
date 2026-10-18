"""Install the pinned NVIDIA local diarization runtime on Apple Silicon."""
from __future__ import annotations

import hashlib
import platform
import shutil
import sys
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config.paths import ProjectPaths
from src.core.diarization import RUNTIME_NAME, MODEL_NAME

RUNTIME_SHA256 = '5cb02ba7c04f0b5585ce5cde9c830be5f0b7dfb4c83083c500109c381b4f2da9'
MODEL_SHA256 = '08456d9e22cd9a323c0364d98375f3746d6e68507ebb705cd46438c534c7a3a1'
REVISION = 'f667ed73aee57d40cc39428eb768b4fd87a0a29e'


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(url: str, path: Path, expected: str) -> None:
    with requests.get(url, stream=True, timeout=(10, 60)) as response:
        response.raise_for_status()
        with path.open('wb') as stream:
            for chunk in response.iter_content(1024 * 1024):
                stream.write(chunk)
    if digest(path) != expected:
        path.unlink(missing_ok=True)
        raise RuntimeError('Download checksum mismatch. Installation stopped.')


def main() -> None:
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise SystemExit('Automatic setup currently supports Apple Silicon Macs. For another platform, install NeMo-Speech.cpp and set SUBTEXT_DIARIZATION_BIN and SUBTEXT_DIARIZATION_MODEL to local files.')
    root = ProjectPaths.RUNTIME_DIR / 'diarization'
    root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='setup_', dir=root) as temporary:
        temp = Path(temporary)
        binary = root / 'runtime' / RUNTIME_NAME / 'bin/nemo-speech'
        if not binary.exists():
            archive = temp / 'runtime.tar.gz'
            print('Installing the NVIDIA runtime…', flush=True)
            download(f'https://github.com/NVIDIA/NeMo-Speech.cpp/releases/download/v0.2.0/{RUNTIME_NAME}.tar.gz', archive, RUNTIME_SHA256)
            with tarfile.open(archive) as bundle:
                bundle.extractall(temp / 'unpacked', filter='data')
            shutil.copytree(temp / 'unpacked' / RUNTIME_NAME, root / 'runtime' / RUNTIME_NAME, dirs_exist_ok=True)
        model = root / MODEL_NAME
        if not model.is_file() or digest(model) != MODEL_SHA256:
            cached = ProjectPaths.BASE_DIR / 'benchmarks/diarization/models/nvidia/Nemotron-3-Diarization' / REVISION / MODEL_NAME
            staged = temp / MODEL_NAME
            if cached.is_file() and digest(cached) == MODEL_SHA256:
                shutil.copyfile(cached, staged)
            else:
                print('Downloading the NVIDIA model (~102 MiB)…', flush=True)
                download(f'https://huggingface.co/nvidia/Nemotron-3-Diarization/resolve/{REVISION}/{MODEL_NAME}', staged, MODEL_SHA256)
            staged.replace(model)
    print('Identify speakers is ready. Models and runtime stay local in assets/runtime/diarization.')


if __name__ == '__main__':
    main()

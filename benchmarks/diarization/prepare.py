"""Fetch pinned public reference audio without downloading videos."""
import hashlib
import io
import json
import tarfile
import wave
from pathlib import Path
import requests
from remotezip import RemoteZip

ROOT = Path(__file__).resolve().parent

def save(url: str, path: Path) -> None:
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)

def main() -> None:
    sources = json.loads((ROOT / 'sources.json').read_text())
    data = ROOT / 'data'
    data.mkdir(exist_ok=True)
    samples = []
    # NVIDIA distributes this AMI excerpt as a public runtime fixture.
    name = 'ami_en2002d_2132'
    base = f"https://raw.githubusercontent.com/NVIDIA/NeMo-Speech.cpp/{sources['nemo_revision']}/test_files/diar"
    for ext in ['wav', 'rttm', 'json']:
        save(f'{base}/{name}.{ext}', data / f'{name}.{ext}')
    samples.append({'id': name, 'dataset': 'AMI', 'source': base, 'role': 'smoke-test; NVIDIA-distributed fixture, not independent'})
    # Select solely by reference duration and speaker count, before model runs.
    rev = sources['vox_revision']
    response = requests.get(f'https://api.github.com/repos/joonson/voxconverse/tarball/{rev}', timeout=60)
    response.raise_for_status()
    candidates = []
    with tarfile.open(fileobj=io.BytesIO(response.content), mode='r:gz') as archive:
        for member in archive:
            if '/test/' not in member.name or not member.name.endswith('.rttm'):
                continue
            content = archive.extractfile(member).read()
            rows = [line.split() for line in content.decode().splitlines() if line.startswith('SPEAKER')]
            end = max(float(row[3]) + float(row[4]) for row in rows)
            count = len({row[7] for row in rows})
            if 45 <= end <= 180:
                candidates.append((count, Path(member.name).stem, content))
    chosen = []
    for count in [2, 3, 4]:
        chosen.append(sorted(item for item in candidates if item[0] == count)[0])
    url = 'https://www.robots.ox.ac.uk/~vgg/data/voxconverse/data/voxconverse_test_wav.zip'
    with RemoteZip(url, timeout=60) as archive:
        for count, name, content in chosen:
            entry = next(n for n in archive.namelist() if n.endswith('/'+name+'.wav') or n == name+'.wav')
            (data / f'{name}.wav').write_bytes(archive.read(entry))
            (data / f'{name}.rttm').write_bytes(content)
            samples.append({'id': name, 'dataset': 'VoxConverse v0.3 test', 'source': url, 'reference_speakers': count, 'role': 'public benchmark; possible model development exposure'})
    for sample in samples:
        name = sample['id']
        with wave.open(str(data / f'{name}.wav')) as audio:
            sample['duration_seconds'] = audio.getnframes() / audio.getframerate()
        sample['audio'] = f'data/{name}.wav'
        sample['reference'] = f'data/{name}.rttm'
        sample['sha256'] = {ext: hashlib.sha256((data / f'{name}.{ext}').read_bytes()).hexdigest() for ext in ['wav', 'rttm']}
    (ROOT / 'manifest.json').write_text(json.dumps(samples, indent=2)+'\n')
    print(json.dumps([{k:s[k] for k in ['id','dataset','duration_seconds']} for s in samples],indent=2))

if __name__ == '__main__':
    main()

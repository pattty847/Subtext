"""Compare local social-clip runs without inventing reference accuracy scores."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent


def speaker_activity(path: Path) -> dict[str, Any]:
    durations: dict[str, float] = defaultdict(float)
    turns: dict[str, int] = defaultdict(int)
    events: list[tuple[float, int]] = []
    for line in path.read_text().splitlines():
        fields = line.split()
        if not fields or fields[0] != 'SPEAKER':
            continue
        start, duration = float(fields[3]), float(fields[4])
        speaker = fields[7]
        durations[speaker] += duration
        turns[speaker] += 1
        events.extend([(start, 1), (start + duration, -1)])
    overlap, active, previous = 0.0, 0, 0.0
    for timestamp, delta in sorted(events):
        if active >= 2:
            overlap += timestamp - previous
        active += delta
        previous = timestamp
    return {'speaker_seconds': dict(sorted(durations.items())), 'turn_counts': dict(sorted(turns.items())), 'predicted_overlap_seconds': overlap}


def main() -> None:
    samples = json.loads((ROOT / 'social-manifest.json').read_text())
    records: dict[tuple[str, str], dict[str, Any]] = {}
    sources: dict[tuple[str, str], str] = {}
    for path in sorted((ROOT / 'results').glob('report-*.json')):
        report = json.loads(path.read_text())
        for row in report['runs']:
            if row.get('status') == 'ok' and any(sample['id'] == row.get('sample') for sample in samples):
                key = row['model'], row['sample']
                records[key] = row
                sources[key] = path.name
    title = {'tiktok_solo_speech': 'Solo speech', 'tiktok_singing': 'Singing', 'instagram_game_chat': 'Game chat', 'instagram_street_interview': 'Street interview', 'instagram_debate': 'Debate', 'instagram_judge': 'Judge'}
    lines = ['# Social-clip diarization comparison', '', 'Automatic speaker detection on downloaded local audio only. User speaker-count notes are review expectations, not timestamped ground truth. No DER or speaker-attribution accuracy can be calculated yet. A correct count can still hide incorrect assignments.', '', '| Clip | Duration | User expectation | NVIDIA labels | Pyannote labels | NVIDIA seconds | Pyannote seconds |', '|---|---:|---|---:|---:|---:|---:|']
    details = []
    for sample in samples:
        sid = sample['id']
        rows = [records.get((model, sid)) for model in ['nvidia', 'pyannote']]
        counts = [str(row['predicted_speakers']) if row else 'pending' for row in rows]
        elapsed = [f"{row['wall_seconds']:.2f}" if row else 'pending' for row in rows]
        lines.append(f"| {title[sid]} | {sample['duration_seconds']:.1f}s | {sample['expected_speakers_note']} | {counts[0]} | {counts[1]} | {elapsed[0]} | {elapsed[1]} |")
        detail = {'sample': sid, 'duration_seconds': sample['duration_seconds'], 'user_note': sample['expected_speakers_note'], 'models': {}}
        for model, row in zip(['nvidia', 'pyannote'], rows):
            if row:
                backend = row['backend']
                path = ROOT / 'results' / f'{model}-{backend}-{sid}.rttm'
                detail['models'][model] = {**row, **speaker_activity(path), 'source_report': sources[(model, sid)]}
        details.append(detail)
    lines += ['', '## Interpretation limits', '', '- NVIDIA: Nemotron 3 Q8_0, NeMo-Speech.cpp 0.2.0, Metal, v3-offline preset. Pyannote: Community-1 default float32 on CPU. Speed compares these deployments, not model architecture on identical hardware.', '- Timing includes fresh process/model loading after caches have been populated; it excludes model download and the separate pyannote warmup. GPU compilation and OS caching can affect results.', '- Process-tree RSS is sampled and excludes GPU allocations and OS cache; it is not total Apple unified-memory use.', '- Speaker IDs are local to each clip/model. A matching label number across models has no identity meaning.', '- Both models receive only the audio, never the user-provided speaker-count notes.', '- Singing, backing vocals, audience reactions, overlap, and edited-in voices need listening before labeling any count as definitively right or wrong.', '', '## Speaker activity diagnostics', '']
    for detail in details:
        lines.append('### ' + title[detail['sample']])
        lines.append('')
        for model, row in detail['models'].items():
            values = ', '.join(f'{speaker}: {seconds:.2f}s' for speaker, seconds in row['speaker_seconds'].items())
            lines.append(f"- {model}: {values}. Predicted overlap: {row['predicted_overlap_seconds']:.2f}s.")
        lines.append('')
    (ROOT / 'results/social-summary.md').write_text('\n'.join(lines) + '\n')
    (ROOT / 'results/social-comparison.json').write_text(json.dumps(details, indent=2) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()

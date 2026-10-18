"""Sequential local diarization benchmark; no app integration or cloud inference."""
import argparse
import hashlib
from datetime import datetime, timezone
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault('MPLCONFIGDIR', str(ROOT / 'results' / 'mpl-cache'))
os.environ.setdefault('PYANNOTE_METRICS_ENABLED', '0')
MODEL = 'pyannote/speaker-diarization-community-1'
MODEL_REVISION = json.loads((ROOT/'sources.json').read_text()).get('pyannote_revision')

def score(reference: Path, hypothesis: Path, duration: float) -> dict:
    from pyannote.core import Segment, Timeline
    from pyannote.database.util import load_rttm
    from pyannote.metrics.diarization import DiarizationErrorRate
    ref = next(iter(load_rttm(reference).values()))
    hyp = next(iter(load_rttm(hypothesis).values()), None)
    if hyp is None:
        from pyannote.core import Annotation
        hyp = Annotation(uri=ref.uri)
    hyp.uri = ref.uri
    result = {'reference_speakers': len(ref.labels()), 'predicted_speakers': len(hyp.labels())}
    for collar in [0.0, 0.25]:
        metric = DiarizationErrorRate(collar=collar, skip_overlap=False)
        detail = metric(ref, hyp, uem=Timeline([Segment(0, duration)], uri=ref.uri), detailed=True)
        total = detail['total']
        result[f'DER_collar_{collar}'] = detail['diarization error rate']
        if collar == 0:
            result.update({k.replace(' ', '_')+'_seconds': detail[k] for k in ['total','confusion','missed detection','false alarm']})
            result['speaker_confusion_rate'] = detail['confusion']/total if total else 0
    return result

def pyannote_worker(audio: Path, output: Path) -> None:
    # Loading one model per subprocess bounds memory; predecode avoids torchcodec issues.
    os.environ['PYANNOTE_METRICS_ENABLED'] = '0'
    import soundfile as sf
    import torch
    from pyannote.audio import Pipeline
    from huggingface_hub import get_token
    pipeline = Pipeline.from_pretrained(MODEL, revision=MODEL_REVISION, token=get_token())
    if pipeline is None:
        raise RuntimeError('Community-1 unavailable; approve access and log in locally.')
    pipeline.to(torch.device('cpu'))
    audio_data, sample_rate = sf.read(audio, dtype='float32', always_2d=True)
    waveform = torch.from_numpy(audio_data.T.copy())
    result = pipeline({'waveform': waveform, 'sample_rate': sample_rate})
    annotation = result.speaker_diarization
    annotation.uri = audio.stem
    with output.open('w') as stream:
        annotation.write_rttm(stream)

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=['nvidia','pyannote','all'], default='all')
    parser.add_argument('--device', choices=['metal','cpu'], default='metal', help='NVIDIA backend; pyannote runs CPU')
    parser.add_argument('--sample', help='Optional manifest sample ID')
    parser.add_argument('--manifest', type=Path, default=ROOT/'manifest.json')
    parser.add_argument('--offline', action='store_true', help='Use cached model files only; no network access')
    parser.add_argument('--worker', nargs=2, metavar=('AUDIO','RTTM'))
    args = parser.parse_args()
    if args.offline:
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
    if args.worker:
        pyannote_worker(*map(Path,args.worker))
        return
    import psutil
    import importlib.metadata
    from huggingface_hub import get_token
    samples = json.loads(args.manifest.read_text())
    samples = [s for s in samples if not args.sample or s['id']==args.sample]
    if not samples:
        parser.error('No matching samples')
    results = ROOT / 'results'
    results.mkdir(exist_ok=True)
    for sample in samples:
        for ext, expected in sample['sha256'].items():
            actual = hashlib.sha256((ROOT / sample['audio' if ext=='wav' else 'reference']).read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError(f'Checksum mismatch: {sample["id"]}.{ext}')
    models = ['nvidia','pyannote'] if args.model=='all' else [args.model]
    report = {'system':{'platform':platform.platform(),'machine':platform.machine(),'ram_bytes':psutil.virtual_memory().total},'protocol':{'speaker_count':'auto; no reference count supplied','overlap':'included','collars_seconds':[0,0.25],'runtime':'fresh subprocess per file; includes load, excludes model download','memory':'sampled process-tree RSS; excludes GPU allocations and OS cache; not total unified-memory use'},'runs':[]}
    report['protocol']['offline'] = args.offline
    report['created_at_utc'] = datetime.now(timezone.utc).isoformat()
    report['versions'] = {name: importlib.metadata.version(name) for name in ['pyannote.audio','pyannote.metrics','torch','torchaudio','psutil']}
    report['models'] = {'nvidia': {'id':'nvidia/Nemotron-3-Diarization','revision':'f667ed73aee57d40cc39428eb768b4fd87a0a29e','runtime':'NeMo-Speech.cpp 0.2.0','precision':'Q8_0','preset':'v3-offline'}, 'pyannote': {'id':MODEL,'precision':'default float32','backend':'cpu','revision':MODEL_REVISION}}
    report_path = results / ('report-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    for model in models:
        if model=='pyannote' and not get_token():
            report['runs'].append({'model':model,'status':'blocked','reason':'No local HF login. Accept Community-1 conditions and run hf auth login.'})
            continue
        if model=='pyannote':
            # Fetch before measuring inference; token never enters command-line arguments.
            from huggingface_hub import snapshot_download
            try:
                snapshot = snapshot_download(MODEL, revision=MODEL_REVISION, local_files_only=args.offline)
                report['models']['pyannote']['revision'] = Path(snapshot).name
                # Initialize separately so downloads/initial setup are outside timing.
                warmup = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker', str(ROOT/samples[0]['audio']), str(results/'pyannote-warmup.rttm')], stdout=(results/'pyannote-warmup.log').open('w'), stderr=subprocess.STDOUT, timeout=1800)
                if warmup.returncode:
                    raise RuntimeError('Pyannote warmup failed; inspect results/pyannote-warmup.log')
            except Exception as exc:
                report['runs'].append({'model':model,'status':'blocked','reason':f'Model prefetch failed ({type(exc).__name__}); check gated access.'})
                continue
        for sample in samples:
            name=sample['id']
            out=results / f'{model}-{args.device if model=="nvidia" else "cpu"}-{name}.rttm'
            log=out.with_suffix('.log')
            if model=='nvidia':
                binary=ROOT / 'runtime/nemo-speech-0.2.0-macos-aarch64-metal/bin/nemo-speech'
                command=[str(binary),'diarize',str(ROOT/sample['audio']),'--model',str(ROOT/'models/nvidia/Nemotron-3-Diarization/f667ed73aee57d40cc39428eb768b4fd87a0a29e/Nemotron-3-Diarization.q8_0.gguf') if args.offline else 'nvidia/Nemotron-3-Diarization','--device',args.device,'--preset','v3-offline','--format','rttm','--recording-id',name,'--output',str(out),'--force']
            else:
                command=[sys.executable,str(Path(__file__).resolve()),'--worker',str(ROOT/sample['audio']),str(out)]
            env=os.environ.copy()
            env['NEMO_SPEECH_MODEL_DIR']=str(ROOT/'models')
            env['PYANNOTE_METRICS_ENABLED']='0'
            start=time.perf_counter()
            peak=0
            with log.open('w') as stream:
                process=subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT,env=env)
                monitor=psutil.Process(process.pid)
                while process.poll() is None:
                    try:
                        tree=[monitor]+monitor.children(recursive=True)
                        peak=max(peak,sum(p.memory_info().rss for p in tree if p.is_running()))
                    except (psutil.NoSuchProcess,psutil.AccessDenied,PermissionError):
                        pass
                    if time.perf_counter()-start>1800:
                        process.kill()
                        process.wait()
                        break
                    time.sleep(0.05)
            elapsed=time.perf_counter()-start
            row={'model':model,'sample':name,'backend':args.device if model=='nvidia' else 'cpu','status':'ok' if process.returncode==0 else 'failed','wall_seconds':elapsed,'real_time_factor':elapsed/sample['duration_seconds'],'peak_process_tree_rss_mib':peak/1024**2 if peak else None,'log':str(log.relative_to(ROOT))}
            if process.returncode==0:
                if sample.get('reference'):
                    row.update(score(ROOT/sample['reference'],out,sample['duration_seconds']))
                else:
                    labels = {line.split()[7] for line in out.read_text().splitlines() if line.startswith('SPEAKER')}
                    row['predicted_speakers'] = len(labels)
                    row['reference_status'] = 'unannotated; no accuracy score'
                    row['user_note'] = sample.get('expected_speakers_note')
            report['runs'].append(row)
            report_path.write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(row),flush=True)
    report_path.write_text(json.dumps(report,indent=2)+'\n')
    (results/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Report:',report_path)

if __name__=='__main__':
    main()

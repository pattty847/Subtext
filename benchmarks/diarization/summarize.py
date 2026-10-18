"""Summarize latest successful public runs; preserve per-model report sources."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def main() -> None:
    records={}
    sources={}
    for path in sorted((ROOT/'results').glob('report-*.json')):
        report=json.loads(path.read_text())
        for row in report['runs']:
            if row.get('status')=='ok' and 'DER_collar_0.0' in row:
                records[(row['model'],row['sample'])]=row
                sources[(row['model'],row['sample'])]=path.name
    text=['# Public diarization pilot results','', 'Lower error is better. Auto speaker count; overlap included. Strict DER has zero boundary collar. NVIDIA uses Q8_0 on Metal; pyannote uses default float32 on CPU. Timing includes process/model loading and is cache-sensitive. These are practical runtime configurations, not a controlled architecture speed comparison.','', '| Sample | Reference speakers | Model | Detected speakers | Strict DER | Speaker confusion | Wall seconds | Process RSS MiB* |','|---|---:|---|---:|---:|---:|---:|---:|']
    for (model,sample),r in sorted(records.items(),key=lambda item:(item[0][1],item[0][0])):
        rss=r.get('peak_process_tree_rss_mib')
        text.append(f"| {sample} | {r['reference_speakers']} | {model} | {r['predicted_speakers']} | {r['DER_collar_0.0']:.1%} | {r['speaker_confusion_rate']:.1%} | {r['wall_seconds']:.2f} | {rss:.0f} |" if rss is not None else f"| {sample} | {r['reference_speakers']} | {model} | {r['predicted_speakers']} | {r['DER_collar_0.0']:.1%} | {r['speaker_confusion_rate']:.1%} | {r['wall_seconds']:.2f} | unavailable |")
    text+=['','*Sampled process-tree RSS excludes GPU allocations and OS cache; it is not total unified-memory use.','', '## VoxConverse-only aggregate','', 'AMI is a NVIDIA-distributed smoke fixture and is excluded from this aggregate. Public datasets may have development exposure. Three selected clips are not enough for a general model ranking.']
    aggregate={}
    for model in ['nvidia','pyannote']:
        rows=[r for (m,s),r in records.items() if m==model and s!='ami_en2002d_2132']
        if len(rows)!=3:
            text.append(f'\n{model}: incomplete ({len(rows)}/3 clips).')
            continue
        total=sum(r['total_seconds'] for r in rows)
        error=sum(r['confusion_seconds']+r['missed_detection_seconds']+r['false_alarm_seconds'] for r in rows)
        confusion=sum(r['confusion_seconds'] for r in rows)
        aggregate[model]={'strict_DER':error/total,'speaker_confusion':confusion/total,'files':len(rows)}
        text.append(f'\n{model}: strict DER **{error/total:.1%}**; speaker confusion **{confusion/total:.1%}** (weighted by reference speaker-time).')
    text+=['','## Source reports','']+['- '+name for name in sorted(set(sources.values()))]
    (ROOT/'results/summary.md').write_text('\n'.join(text)+'\n')
    (ROOT/'results/aggregate.json').write_text(json.dumps(aggregate,indent=2)+'\n')
    print('\n'.join(text))

if __name__=='__main__':
    main()

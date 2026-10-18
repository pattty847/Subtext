"""Render speaker-turn timelines for reviewing the cached social clips."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault('MPLCONFIGDIR', str(ROOT/'results/mpl-cache'))


def main() -> None:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    samples = json.loads((ROOT/'social-manifest.json').read_text())
    fig, axes = plt.subplots(len(samples), 2, figsize=(15, 14), layout='constrained')
    palette = plt.get_cmap('tab10')
    titles = {'tiktok_solo_speech':'Solo speech', 'tiktok_singing':'Singing', 'instagram_game_chat':'Game chat', 'instagram_street_interview':'Street interview', 'instagram_debate':'Debate', 'instagram_judge':'Judge'}
    for row, sample in enumerate(samples):
        for col, (model, backend) in enumerate([('nvidia','metal'),('pyannote','cpu')]):
            ax=axes[row,col]
            path=ROOT/'results'/f'{model}-{backend}-{sample["id"]}.rttm'
            turns=[]
            if path.is_file():
                for line in path.read_text().splitlines():
                    parts=line.split()
                    if parts and parts[0]=='SPEAKER':
                        turns.append((float(parts[3]),float(parts[4]),parts[7]))
            labels=sorted({turn[2] for turn in turns})
            for index,label in enumerate(labels):
                spans=[(start,duration) for start,duration,speaker in turns if speaker==label]
                ax.broken_barh(spans,(index-0.32,0.64),facecolors=palette(index))
            ax.set_yticks(range(len(labels)),[f'Label {i+1}' for i in range(len(labels))])
            ax.set_ylim(-0.7,max(0,len(labels)-1)+0.7)
            ax.set_xlim(0,sample['duration_seconds'])
            ax.set_title(f'{titles[sample["id"]]} — {"NVIDIA" if model=="nvidia" else "pyannote"}',loc='left',fontsize=11,fontweight='bold')
            ax.set_xlabel('Seconds',fontsize=9)
            ax.grid(axis='x',alpha=.2)
            ax.spines[['top','right']].set_visible(False)
            if not labels:
                ax.text(.5,.5,'No completed prediction',ha='center',transform=ax.transAxes)
    fig.suptitle('Social clips: predicted speaker activity\nLabels and colors are independent per model/clip; matching colors do not establish identity.',fontsize=15)
    fig.savefig(ROOT/'results/social-timelines.png',dpi=150)
    plt.close(fig)
    print(ROOT/'results/social-timelines.png')


if __name__=='__main__':
    main()

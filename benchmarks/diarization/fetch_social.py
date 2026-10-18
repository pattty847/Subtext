"""Download user-selected short clips anonymously; never import browser cookies."""
import json
import hashlib
import wave
from pathlib import Path
import subprocess
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

ROOT=Path(__file__).resolve().parent

def main() -> None:
    samples=json.loads((ROOT/'social-samples.json').read_text())
    directory=ROOT/'data/social'
    directory.mkdir(parents=True,exist_ok=True)
    statuses=[]
    manifest=[]
    for sample in samples:
        name=sample['id']
        wav=directory/f'{name}.wav'
        try:
            if not wav.exists():
                options={'quiet':True,'noprogress':True,'max_filesize':100*1024*1024,'no_warnings':True,'format':'bestaudio/best','noplaylist':True,'socket_timeout':15,'retries':0,'extractor_retries':0,'outtmpl':str(directory/f'{name}.%(ext)s')}
                with YoutubeDL(options) as ydl:
                    metadata=ydl.extract_info(sample['url'],download=False)
                    if not metadata or (metadata.get('duration') and metadata['duration']>300):
                        raise ValueError('No metadata or over 5-minute sample limit')
                    ydl.download([sample['url']])
                media=next(path for path in directory.glob(name+'.*') if path.suffix not in ['.wav','.part','.ytdl'])
                subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',str(media),'-t','300','-ac','1','-ar','16000',str(wav)],check=True)
            with wave.open(str(wav)) as audio:
                duration=audio.getnframes()/audio.getframerate()
            manifest.append({**sample, 'audio':str(wav.relative_to(ROOT)), 'duration_seconds':duration, 'sha256':{'wav':hashlib.sha256(wav.read_bytes()).hexdigest()}})
            status={'id':name,'status':'audio_ready','audio':str(wav.relative_to(ROOT)),'reference_status':'unannotated; do not calculate DER'}
        except (DownloadError,ValueError,subprocess.CalledProcessError) as exc:
            status={'id':name,'status':'retrieval_failed','error_type':type(exc).__name__,'reference_status':'unannotated'}
        statuses.append(status)
        (ROOT/'results/social-retrieval.json').write_text(json.dumps(statuses,indent=2)+'\n')
        (ROOT/'social-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        print(json.dumps(status),flush=True)

if __name__=='__main__':
    main()

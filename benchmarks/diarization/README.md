# Local speaker diarization benchmark

This is an isolated evaluation, not a Subtext feature or a replacement for the app environment. Both models receive audio only and infer speakers automatically. Reference speaker counts are never passed to inference. Whisper transcription and word alignment are intentionally excluded to isolate diarization accuracy.

## Setup and run on Apple Silicon

From the repository root, use `bash benchmarks/diarization/setup.sh`. This installs a separate Python environment and NVIDIA's SHA-256-verified macOS Metal runtime locally. Model/audio downloads and results are ignored by Git. The pinned Python dependency set is in `requirements-lock.txt`; dataset source commits and the Community-1 model revision are in `sources.json`.

For Community-1, first accept conditions at https://huggingface.co/pyannote/speaker-diarization-community-1, then run `benchmarks/diarization/.venv/bin/hf auth login` locally. Never paste credentials into chat, scripts, command arguments, or tracked files. The existing Hugging Face credential is reused; no credential is saved in this repository. Pyannote telemetry is disabled by the runner.

Run with:

```bash
benchmarks/diarization/.venv/bin/python benchmarks/diarization/benchmark.py --model all
benchmarks/diarization/.venv/bin/python -m unittest discover -s benchmarks/diarization -p 'test_*.py'
```

Use `--model nvidia` or `--model pyannote` to run one side, `--sample eazeq` for one recording, and `--device cpu` for a NVIDIA CPU comparison. Pyannote uses CPU. NVIDIA uses the official Q8_0 GGUF model and `v3-offline` chunk configuration on Metal by default. This compares practical local configurations, not identical hardware or precision. Do not interpret speed differences as architecture-only results. Inference is sequential in fresh subprocesses, and the pyannote initialization/warmup precedes measurement.

## Samples and scoring

`manifest.json` records audio duration, source, reference path and SHA-256 checksums. Preparation selects the alphabetically first test clip lasting 45-180 seconds for each reference speaker count 2, 3 and 4, before model inference. These are public benchmarks with possible model-development exposure, not an unseen evaluation.

- VoxConverse v0.3: `eazeq`, `bvyvm`, `aepyx`. Source: https://github.com/joonson/voxconverse . Audio is retrieved by ZIP range requests from Oxford's official distribution. Research dataset distributed under CC BY 4.0; original media copyright stays with its owners. Cite Chung et al., *Spot the conversation: speaker diarisation in the wild*, Interspeech 2020. Preserve source/license attribution if sharing results or excerpts.
- AMI `EN2002d`, 60 seconds from 2132.5 seconds: official NVIDIA runtime fixture with matching reference, CC BY 4.0 audio/word annotations and Apache-2.0 reference preparation. Attribution: AMI Meeting Corpus (https://groups.inf.ed.ac.uk/ami/corpus/), BUTSpeechFIT AMI-diarization-setup and NVIDIA fixture README. This NVIDIA-distributed fixture is a smoke test, not independent evidence of model superiority.

The scorer uses pyannote.metrics with optimal speaker-label mapping and the full audio duration as the evaluation region. Overlap is included. It reports strict DER (zero collar), DER with a 0.25-second boundary collar, confusion, missed speech, false alarms and speaker counts. DER uses reference speaker-time, which can exceed wall time during overlap. Empty predictions count as missed speech. Speaker-label permutations are equivalent; merging people is penalized.

Timing includes subprocess/model loading after model downloads; first-run Metal compilation/cache costs can dominate. Fresh processes still share OS/model/GPU caches. Peak sampled process-tree RSS excludes GPU allocations and OS cache and must not be treated as total unified-memory use. Results are not a battery of repeated timing trials. Every run has a timestamped JSON report in `results/`; `report.json` is the latest run, not a merged scoreboard. Logs/RTTM files are replaced on reruns of the same model/sample. Do not run two benchmark invocations concurrently.

## User-selected social clips

`social-samples.json` records user descriptions and unverified count notes separately from the scored public manifest. No reference count is supplied to models. Missing Judge Levy URL and the absent reaction clip are omitted.

Fetch with the application's yt-dlp environment:

```bash
uv run --no-sync python benchmarks/diarization/fetch_social.py
```

The fetcher uses anonymous requests, imports no browser cookies, and caps conversion at five minutes. Social recordings need listening and timestamped reference annotation before DER can be reported. Audience vocalizations and backing vocals need explicit labeling decisions. Predictions alone cannot establish ground truth. Retrieval status is in `results/social-retrieval.json`.

Run predictions on retrieved social audio with `benchmarks/diarization/.venv/bin/python benchmarks/diarization/benchmark.py --manifest benchmarks/diarization/social-manifest.json --model all`. This reports predicted counts and timings only. Counts from the user remain unverified notes and are not inference parameters or accuracy scores.

Generate a combined public-results table with `benchmarks/diarization/.venv/bin/python benchmarks/diarization/summarize.py`. It selects the latest successful scored result per model/sample from timestamped reports; it excludes unannotated social recordings from accuracy summaries.

## Initial public pilot

Both models completed all four public recordings on the local Apple Silicon Mac. See `results/summary.md` for the generated comparison. On the three VoxConverse samples, pyannote matched all reference speaker counts (2, 3, 4); NVIDIA returned (2, 4, 5). Neither matched the 4-speaker AMI excerpt (NVIDIA 3, pyannote 2). This is a small descriptive pilot, not evidence of universal superiority. The five user-selected social clips have been retrieved but remain unannotated and unscored.

For already-downloaded samples, add `--offline` to the benchmark command. This sets Hugging Face/Transformers offline mode, resolves Community-1 from its local pinned cache, and passes NVIDIA the existing local GGUF path. It does not invoke the social fetcher or any Instagram code. Run `benchmarks/diarization/.venv/bin/python benchmarks/diarization/summarize_social.py` for count/timing comparisons and speaker-activity diagnostics. These diagnostics are not accuracy scores without timestamped reference labels.

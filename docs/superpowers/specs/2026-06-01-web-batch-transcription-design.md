# Web Batch Transcription Design

Date: 2026-06-01

## Summary

Add a private web service workflow for transcribing multiple direct media URLs in one run. The user can paste several links into the existing web URL field, tap the existing Transcribe button, and receive one combined transcript document that can be copied, downloaded, or sent to the existing chat context.

This first version intentionally does not expand Instagram profiles, channels, playlists, or creator pages into lists of videos. The user will manually choose the specific videos they want analyzed.

## Goals

- Keep the feature web-first, because the private Tailscale web service is the primary workflow for this use case.
- Let users paste batches from a phone without needing a formal queue UI.
- Preserve the existing single-URL behavior.
- Produce an AI-ready combined transcript with clear per-source boundaries.
- Continue processing later URLs if one URL fails.
- Keep heavy work sequential for memory stability.

## Non-Goals

- No Instagram profile, channel, playlist, or search-result expansion in this version.
- No separate transcript zip download in this version.
- No combined media-file download or media concatenation.
- No automatic frontier-model analysis handoff.
- No desktop parity unless requested later.

## User Experience

The existing URL input becomes a compact textarea so pasted batches can contain new lines on mobile.

Supported separators:

- Newlines
- Commas
- Semicolons
- Whitespace between full `http://` or `https://` URLs where practical

The primary button remains labeled `Transcribe` for both single and batch runs.

When more than one URL is detected, the web UI shows a small count such as `3 links detected`. This is informational only; the user does not need to manage a queue.

During a batch run, status text shows progress such as `Transcribing 2 of 5...`. The result area remains the same transcript output panel used today.

After completion, Copy, Download `.txt`, and Chat about this operate on the combined transcript text.

## Output Format

Batch output is plain text and easy to paste into ChatGPT, Claude, or another external model:

```text
# Batch Transcript

## 1. https://example.com/video-one
Status: transcribed

Transcript text...

## 2. https://example.com/video-two
Status: error
Error: Download failed: ...

## 3. https://example.com/video-three
Status: transcribed

Transcript text...
```

URL-only headings are the first implementation target. Video titles can be added in a later enhancement if yt-dlp metadata is exposed cleanly.

## Architecture

### Frontend

Update `src/web/static/index.html`, `src/web/static/app.js`, and `src/web/static/style.css`.

Responsibilities:

- Allow multi-line URL input.
- Parse and count candidate URLs client-side for feedback.
- Submit the raw URL text to the server.
- Read streamed batch events and append combined transcript text as each item completes.
- Keep existing single-file upload behavior unchanged.

### Server

Update `src/web/server.py`.

Responsibilities:

- Parse URL form input into one or more direct URLs.
- Keep the existing single-file upload path unchanged.
- For a single URL, preserve the current streaming behavior and response shape.
- For multiple URLs, run each URL sequentially behind the existing private service lock.
- Emit server-sent events for per-item status, transcript chunks or completed item text, errors, and final duration/latency summary.
- Return HTTP 400 if no valid URLs are found or if the request mixes multiple URLs with an uploaded file.

### Core

Add a focused URL-list parser to `src/core/input_processor.py`. It will not change the existing desktop mixed file/URL parser semantics unless tests are updated intentionally.

Do not add profile/channel expansion to `src/core/downloader.py` in this version.

## Data Flow

1. User pastes one or more direct URLs into the web URL field.
2. Frontend displays a detected link count if multiple URLs are present.
3. User taps `Transcribe`.
4. Frontend posts the raw URL text to `/transcribe/stream`.
5. Server parses the text into a URL list.
6. If there is one URL, server uses the current single-URL streaming path.
7. If there are multiple URLs, server processes each URL sequentially:
   - download media with `UniversalDownloader.download`
   - transcribe with the warm Whisper transcriber
   - clean up temporary media
   - emit a completed section or error section for that URL
8. Frontend displays the combined transcript in the existing transcript output.
9. User copies, downloads, or attaches the combined transcript to chat.

## Error Handling

- Empty input: show the existing "Paste a URL or choose a file" style message.
- Uploaded file plus URL input: keep the current mutually exclusive rule.
- Multiple URLs plus uploaded file: reject with a clear message.
- Invalid text mixed with valid URLs: ignore non-URL fragments if at least one URL is valid.
- One URL fails in a batch: include an error section for that URL and continue with the rest.
- All URLs fail: the result still shows all error sections and the final status makes clear that nothing was transcribed successfully.
- Client abort or navigation away: rely on the existing abort/recovery behavior where possible.

## Security and Privacy

- Preserve localhost-only binding by default.
- Keep the existing shared-secret and Tailscale-first access model.
- Do not add public fetching endpoints beyond the current private service behavior.
- Do not store pasted URLs or transcripts in new persistent locations unless the user explicitly downloads or chats with the transcript through existing flows.

## Testing

Implementation includes focused tests for URL parsing:

- single URL
- comma-separated URLs
- newline-separated URLs
- semicolon-separated URLs
- text with repeated whitespace
- invalid text plus one valid URL

Manual verification:

- `uv run python run_web.py`
- `curl http://127.0.0.1:8000/health`
- Single URL transcription still works.
- Local file transcription still works.
- Two or three direct video URLs produce one combined transcript.
- A batch with one intentionally bad URL continues and includes an error section.
- Copy, Download `.txt`, and Chat about this use the combined transcript.

## Deferred Work

- Instagram profile/channel expansion with a user-selected limit.
- Playlist/channel support for other platforms.
- Separate transcript zip download.
- Batch media download mode.
- Frontier-model backend integration for grounded external-world analysis.

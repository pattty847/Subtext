# Web Batch Transcription Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build web-first batch transcription for multiple direct media URLs with one combined transcript output.

**Architecture:** Add a focused direct-URL parser in `src/core/input_processor.py`, then reuse the existing `/transcribe/stream` SSE endpoint for both single URL and batch URL flows. Batch work runs sequentially through the current downloader/transcriber lock and emits plain text sections through existing `chunk` events, while the frontend upgrades the URL field to a compact textarea with a detected-link count.

**Tech Stack:** Python 3.11, FastAPI, Server-Sent Events, plain browser JavaScript, HTML/CSS, unittest.

---

## File Structure

- Modify `src/core/input_processor.py`: add `parse_url_list(input_text: str) -> list[str]`.
- Create `tests/test_input_processor.py`: test direct URL parsing separators and invalid fragments.
- Modify `src/web/server.py`: parse URL lists in `/transcribe/stream`, preserve single URL behavior, add batch section streaming and per-item error continuation.
- Modify `src/web/static/index.html`: replace single-line URL input with compact textarea and add a detected-link count element.
- Modify `src/web/static/app.js`: count parsed links client-side, keep the Transcribe button label, and keep file/URL mutual exclusion.
- Modify `src/web/static/style.css`: style the textarea and detected-link count for mobile.

## Task 1: URL List Parser

**Files:**
- Modify: `src/core/input_processor.py`
- Test: `tests/test_input_processor.py`

- [ ] **Step 1: Write the failing parser tests**

```python
import unittest

from src.core.input_processor import InputProcessor


class InputProcessorUrlListTests(unittest.TestCase):
    def test_parse_url_list_accepts_single_url(self):
        self.assertEqual(
            InputProcessor.parse_url_list("https://example.com/video"),
            ["https://example.com/video"],
        )

    def test_parse_url_list_accepts_common_batch_separators(self):
        text = (
            "https://example.com/one, https://example.com/two\n"
            "https://example.com/three; https://example.com/four"
        )

        self.assertEqual(
            InputProcessor.parse_url_list(text),
            [
                "https://example.com/one",
                "https://example.com/two",
                "https://example.com/three",
                "https://example.com/four",
            ],
        )

    def test_parse_url_list_ignores_invalid_fragments(self):
        text = "watch these: nope https://example.com/real and not-a-url"

        self.assertEqual(
            InputProcessor.parse_url_list(text),
            ["https://example.com/real"],
        )

    def test_parse_url_list_removes_duplicates_preserving_order(self):
        text = "https://example.com/a\nhttps://example.com/b\nhttps://example.com/a"

        self.assertEqual(
            InputProcessor.parse_url_list(text),
            ["https://example.com/a", "https://example.com/b"],
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run parser tests to verify red**

Run: `uv run python -m unittest tests.test_input_processor -v`

Expected: FAIL with `AttributeError: type object 'InputProcessor' has no attribute 'parse_url_list'`.

- [ ] **Step 3: Implement `parse_url_list`**

```python
    @staticmethod
    def parse_url_list(input_text: str) -> List[str]:
        """Extract direct HTTP(S) URLs from free-form pasted text."""
        urls: List[str] = []
        seen: set[str] = set()

        for match in re.finditer(r"https?://[^\s,;]+", input_text or "", re.IGNORECASE):
            url = match.group(0).strip().rstrip(").,;]")
            if url and url not in seen:
                urls.append(url)
                seen.add(url)

        return urls
```

- [ ] **Step 4: Run parser tests to verify green**

Run: `uv run python -m unittest tests.test_input_processor -v`

Expected: PASS.

## Task 2: Batch SSE Server Flow

**Files:**
- Modify: `src/web/server.py`

- [ ] **Step 1: Add server helpers**

Add imports and helper functions:

```python
from src.core.input_processor import InputProcessor


def _batch_heading(index: int, url: str, status: str) -> str:
    return f"\n\n## {index}. {url}\nStatus: {status}\n\n"


def _batch_error_section(index: int, url: str, error: str) -> str:
    return f"{_batch_heading(index, url, 'error')}Error: {error}\n"
```

- [ ] **Step 2: Update `/transcribe/stream` URL parsing**

Inside `transcribe_stream`, compute:

```python
    urls = InputProcessor.parse_url_list(url)
    has_url = bool(urls)
    has_file = file is not None and bool(file.filename)
```

Then reject requests where `has_url == has_file`, preserving the current message.

- [ ] **Step 3: Preserve single URL behavior**

In the URL branch, keep the existing streaming path when `len(urls) == 1`, using `urls[0]` instead of `url.strip()`.

- [ ] **Step 4: Add multi-URL batch streaming**

For `len(urls) > 1`, stream:

```python
yield _sse_event("chunk", {"text": "# Batch Transcript\n"})
for index, source_url in enumerate(urls, start=1):
    yield _sse_event(
        "progress",
        {"stage": "batch", "percent": round(((index - 1) / len(urls)) * 100, 1), "message": f"Transcribing {index} of {len(urls)}..."},
    )
    downloaded_path = None
    try:
        async with service._lock:
            downloaded_path = await service.downloader.download(source_url)
            async for text_chunk in service.transcriber.transcribe_stream(downloaded_path):
                if text_chunk:
                    yield _sse_event("chunk", {"text": _batch_heading(index, source_url, "transcribed") if first_chunk else ""})
                    yield _sse_event("chunk", {"text": text_chunk})
    except Exception as error:
        yield _sse_event("chunk", {"text": _batch_error_section(index, source_url, str(error))})
    finally:
        if downloaded_path:
            downloaded_path.unlink(missing_ok=True)
```

Track `first_chunk = True` per URL so each transcript section receives one heading before its transcript text.

- [ ] **Step 5: Emit batch completion**

After all URLs finish, emit:

```python
yield _sse_event("done", {"duration": 0, "latency": round(time.perf_counter() - started_at, 3)})
```

Expected behavior: the frontend already accepts `done` with duration/latency, and the combined transcript text is already in the textarea.

## Task 3: Frontend Batch Input

**Files:**
- Modify: `src/web/static/index.html`
- Modify: `src/web/static/app.js`
- Modify: `src/web/static/style.css`

- [ ] **Step 1: Update HTML**

Replace the URL `<input>` with:

```html
<textarea id="url-input"
          placeholder="Paste one or more video links..."
          autocomplete="off" autocapitalize="off" spellcheck="false"
          rows="2"></textarea>
```

Add after the URL row:

```html
<div id="url-count-hint" class="url-count-hint hidden">1 link detected</div>
```

- [ ] **Step 2: Add client URL parser/counting**

In `app.js`, add:

```javascript
function parseUrlsFromText(text) {
  var seen = {};
  var urls = [];
  var re = /https?:\/\/[^\s,;]+/gi;
  var match;
  while ((match = re.exec(text || '')) !== null) {
    var url = match[0].replace(/[).,;\]]+$/g, '');
    if (url && !seen[url]) {
      seen[url] = true;
      urls.push(url);
    }
  }
  return urls;
}
```

- [ ] **Step 3: Show detected count**

Wire `urlInput` input handling:

```javascript
function updateUrlCountHint() {
  var count = parseUrlsFromText(urlInput.value).length;
  if (count > 1) {
    urlCountHint.textContent = count + ' links detected';
    urlCountHint.classList.remove('hidden');
  } else {
    urlCountHint.classList.add('hidden');
  }
}
```

Call `updateUrlCountHint()` in the existing `urlInput` input listener and after paste.

- [ ] **Step 4: Keep submission raw**

Keep `fd.append('url', url)` as-is so the server receives the full pasted textarea content.

- [ ] **Step 5: Style the textarea and hint**

Add CSS:

```css
.url-row textarea {
  width: 100%;
  min-height: 3.25rem;
  resize: vertical;
}

.url-count-hint {
  margin-top: 0.4rem;
  font-size: 0.82rem;
  color: var(--muted);
}
```

Use the existing color variables and spacing patterns in `style.css`.

## Task 4: Verification

**Files:**
- Modify as needed only if tests reveal a bug.

- [ ] **Step 1: Run parser tests**

Run: `uv run python -m unittest tests.test_input_processor -v`

Expected: PASS.

- [ ] **Step 2: Run existing lightweight tests**

Run: `uv run python -m unittest tests.test_cli tests.test_cli_download_modes -v`

Expected: PASS.

- [ ] **Step 3: Run the web service health check**

Run: `uv run python run_web.py`

Then in another process: `curl http://127.0.0.1:8000/health`

Expected: JSON response with `status` and Whisper model metadata.

- [ ] **Step 4: Manual browser check**

Open `http://127.0.0.1:8000`, paste two direct URLs separated by a comma, and verify the UI shows `2 links detected` before starting.

Expected: Transcribe button still says `Transcribe`.

## Self-Review Notes

- Spec coverage: direct multi-link paste, combined transcript, sequential processing, per-URL errors, and profile/channel deferral are covered.
- Placeholder scan: no TBD/TODO placeholders.
- Type consistency: parser returns `list[str]`; server consumes that list; frontend uses a matching regex for count-only hints.

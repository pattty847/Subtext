(function () {
  const STORAGE_KEY = 'subtext-private-key';
  const form = document.getElementById('transcribe-form');
  const apiKeyInput = document.getElementById('api-key');
  const urlInput = document.getElementById('url-input');
  const fileInput = document.getElementById('file-input');
  const submitBtn = document.getElementById('submit-btn');
  const statusCard = document.getElementById('status-card');
  const statusText = document.getElementById('status-text');
  const resultCard = document.getElementById('result-card');
  const transcriptOutput = document.getElementById('transcript-output');
  const durationPill = document.getElementById('duration-pill');
  const latencyPill = document.getElementById('latency-pill');
  const copyBtn = document.getElementById('copy-btn');

  function showStatus(message) {
    statusCard.classList.remove('hidden');
    statusText.textContent = message;
  }

  function hideStatus() {
    statusCard.classList.add('hidden');
  }

  function hideResult() {
    resultCard.classList.add('hidden');
  }

  function showResult(payload) {
    transcriptOutput.value = payload.text || '';
    durationPill.textContent = 'Duration: ' + (payload.duration || 0).toFixed(2) + 's';
    latencyPill.textContent = 'Latency: ' + (payload.latency || 0).toFixed(2) + 's';
    resultCard.classList.remove('hidden');
  }

  function setBusy(isBusy) {
    submitBtn.disabled = isBusy;
  }

  function flashCopyState(label) {
    const original = copyBtn.textContent;
    copyBtn.textContent = label;
    setTimeout(function () {
      copyBtn.textContent = original;
    }, 1500);
  }

  function fallbackCopyText(text) {
    transcriptOutput.focus();
    transcriptOutput.removeAttribute('readonly');
    transcriptOutput.select();
    transcriptOutput.setSelectionRange(0, text.length);

    let copied = false;
    try {
      copied = document.execCommand('copy');
    } catch (_) {
      copied = false;
    }

    transcriptOutput.setAttribute('readonly', 'readonly');
    window.getSelection().removeAllRanges();
    return copied;
  }

  apiKeyInput.value = localStorage.getItem(STORAGE_KEY) || '';

  apiKeyInput.addEventListener('input', function () {
    localStorage.setItem(STORAGE_KEY, apiKeyInput.value.trim());
  });

  urlInput.addEventListener('input', function () {
    if (urlInput.value.trim()) {
      fileInput.value = '';
    }
  });

  fileInput.addEventListener('change', function () {
    if (fileInput.files.length) {
      urlInput.value = '';
    }
  });

  form.addEventListener('submit', async function (event) {
    event.preventDefault();
    hideResult();

    const url = urlInput.value.trim();
    const file = fileInput.files[0] || null;

    if (!url && !file) {
      showStatus('Paste a URL or choose one audio/video file.');
      return;
    }

    if (url && file) {
      showStatus('Use either a URL or a file, not both.');
      return;
    }

    const formData = new FormData();
    if (url) {
      formData.append('url', url);
    }
    if (file) {
      formData.append('file', file);
    }

    const headers = {};
    const apiKey = apiKeyInput.value.trim();
    if (apiKey) {
      headers['X-Subtext-Key'] = apiKey;
    }

    setBusy(true);
    showStatus(url ? 'Downloading and transcribing...' : 'Uploading and transcribing...');

    try {
      const response = await fetch('/transcribe', {
        method: 'POST',
        headers: headers,
        body: formData,
      });

      if (!response.ok) {
        const payload = await response.json().catch(function () {
          return { detail: 'Request failed.' };
        });
        throw new Error(payload.detail || 'Request failed.');
      }

      const payload = await response.json();
      hideStatus();
      showResult(payload);
    } catch (error) {
      showStatus(error.message || 'Transcription failed.');
    } finally {
      setBusy(false);
    }
  });

  copyBtn.addEventListener('click', function () {
    const text = transcriptOutput.value;
    if (!text) {
      return;
    }

    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(
        function () {
          flashCopyState('Copied');
        },
        function () {
          if (fallbackCopyText(text)) {
            flashCopyState('Copied');
            return;
          }
          flashCopyState('Select text');
        }
      );
      return;
    }

    if (fallbackCopyText(text)) {
      flashCopyState('Copied');
      return;
    }
    flashCopyState('Select text');
  });
})();

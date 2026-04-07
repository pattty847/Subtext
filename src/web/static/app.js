(function () {
  const STORAGE_KEY = 'subtext-private-key';
  const form = document.getElementById('transcribe-form');
  const serviceMetaCard = document.getElementById('service-meta-card');
  const serviceMetaText = document.getElementById('service-meta-text');
  const apiKeyInput = document.getElementById('api-key');
  const urlInput = document.getElementById('url-input');
  const fileInput = document.getElementById('file-input');
  const submitBtn = document.getElementById('submit-btn');
  const downloadBtn = document.getElementById('download-btn');
  const statusCard = document.getElementById('status-card');
  const statusText = document.getElementById('status-text');
  const resultCard = document.getElementById('result-card');
  const transcriptOutput = document.getElementById('transcript-output');
  const durationPill = document.getElementById('duration-pill');
  const latencyPill = document.getElementById('latency-pill');
  const streamStatusPill = document.getElementById('stream-status-pill');
  const copyBtn = document.getElementById('copy-btn');
  const streamingCursor = document.getElementById('streaming-cursor');
  const streamIndicator = document.getElementById('stream-indicator');
  const streamLabel = document.getElementById('stream-label');
  const analysisCard = document.getElementById('analysis-card');
  const analysisResultCard = document.getElementById('analysis-result-card');
  const presetSelect = document.getElementById('preset-select');
  const styleSelect = document.getElementById('style-select');
  const analysisModelSelect = document.getElementById('analysis-model-select');
  const customPromptField = document.getElementById('custom-prompt-field');
  const customPromptInput = document.getElementById('custom-prompt-input');
  const analyzeBtn = document.getElementById('analyze-btn');
  const clearAnalysisBtn = document.getElementById('clear-analysis-btn');
  const analysisMetaPill = document.getElementById('analysis-meta-pill');
  const analysisDigest = document.getElementById('analysis-digest');
  const analysisItems = document.getElementById('analysis-items');

  let analysisMeta = {
    default_model: '',
    preferred_models: [],
    available_models: [],
    presets: [],
    humor_styles: [],
  };

  function showStatus(message) {
    statusCard.classList.remove('hidden');
    statusText.textContent = message;
  }

  function hideStatus() {
    statusCard.classList.add('hidden');
  }

  function showStreamIndicator(label) {
    streamIndicator.classList.remove('hidden');
    streamLabel.textContent = label || 'Transcribing...';
  }

  function hideStreamIndicator() {
    streamIndicator.classList.add('hidden');
  }

  function hideResult() {
    resultCard.classList.add('hidden');
  }

  function showResult(payload, streaming) {
    transcriptOutput.value = payload.text || '';
    durationPill.textContent = 'Duration: ' + Number(payload.duration || 0).toFixed(2) + 's';
    latencyPill.textContent = 'Latency: ' + Number(payload.latency || 0).toFixed(2) + 's';
    resultCard.classList.remove('hidden');

    if (streaming) {
      streamStatusPill.classList.remove('hidden');
      streamingCursor.classList.remove('hidden');
    } else {
      streamStatusPill.classList.add('hidden');
      streamingCursor.classList.add('hidden');
    }

    if ((payload.text || '').trim()) {
      analysisCard.classList.remove('hidden');
    }
  }

  function appendTranscriptChunk(text) {
    transcriptOutput.value += text;
    transcriptOutput.scrollTop = transcriptOutput.scrollHeight;
  }

  function finalizeTranscript() {
    streamingCursor.classList.add('hidden');
    streamStatusPill.classList.add('hidden');
    streamIndicator.classList.add('hidden');
  }

  function setBusy(isBusy) {
    submitBtn.disabled = isBusy;
    downloadBtn.disabled = isBusy;
  }

  function setAnalyzeBusy(isBusy) {
    analyzeBtn.disabled = isBusy;
    clearAnalysisBtn.disabled = isBusy;
    presetSelect.disabled = isBusy;
    styleSelect.disabled = isBusy;
    analysisModelSelect.disabled = isBusy;
  }

  function persistKey(value) {
    const trimmedValue = value.trim();
    localStorage.setItem(STORAGE_KEY, trimmedValue);

    const encodedValue = encodeURIComponent(trimmedValue);
    if (trimmedValue) {
      document.cookie = 'subtext_key=' + encodedValue + '; path=/; max-age=31536000; samesite=lax';
      return;
    }
    document.cookie = 'subtext_key=; path=/; max-age=0; samesite=lax';
  }

  /** Best-effort parse of RFC 5987 / legacy filename from Content-Disposition. */
  function filenameFromContentDisposition(header) {
    if (!header || typeof header !== 'string') {
      return 'download';
    }
    var utf8 = /filename\*=UTF-8''([^;\n]+)/i.exec(header);
    if (utf8) {
      try {
        return decodeURIComponent(utf8[1].trim().replace(/^["']|["']$/g, ''));
      } catch (_) {}
    }
    var quoted = /filename="([^"]+)"/i.exec(header);
    if (quoted) {
      return quoted[1];
    }
    var plain = /filename=([^;\s]+)/i.exec(header);
    if (plain) {
      return plain[1].trim().replace(/^["']|["']$/g, '');
    }
    return 'download';
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

  function labelFromName(name) {
    return String(name || '')
      .split('_')
      .map(function (part) {
        return part ? part.charAt(0).toUpperCase() + part.slice(1) : '';
      })
      .join(' ');
  }

  function populateSelect(select, items, fallbackValue) {
    select.innerHTML = '';
    items.forEach(function (item) {
      const option = document.createElement('option');
      option.value = item.value;
      option.textContent = item.label;
      select.appendChild(option);
    });

    if (fallbackValue) {
      select.value = fallbackValue;
    }
    if (!select.value && items.length) {
      select.value = items[0].value;
    }
  }

  function renderAnalysisResult(payload) {
    analysisItems.innerHTML = '';

    analysisMetaPill.textContent =
      'Preset: ' + labelFromName(payload.preset) + ' • Style: ' + labelFromName(payload.humor_style) + ' • Model: ' + (payload.model || 'unknown');

    if (payload.digest) {
      analysisDigest.textContent = payload.digest;
      analysisDigest.classList.remove('hidden');
    } else {
      analysisDigest.textContent = '';
      analysisDigest.classList.add('hidden');
    }

    const items = Array.isArray(payload.items) ? payload.items : [];
    if (payload.custom_response) {
      const custom = document.createElement('article');
      custom.className = 'analysis-item';

      const prompt = document.createElement('p');
      prompt.className = 'analysis-item-why';
      prompt.textContent = 'Prompt: ' + (payload.custom_prompt || 'Custom prompt');

      const text = document.createElement('p');
      text.className = 'analysis-item-text';
      text.textContent = payload.custom_response;

      custom.appendChild(prompt);
      custom.appendChild(text);
      analysisItems.appendChild(custom);
    } else if (!items.length) {
      const empty = document.createElement('p');
      empty.className = 'analysis-item-why';
      empty.textContent = 'The model returned no usable ideas.';
      analysisItems.appendChild(empty);
    } else {
      items.forEach(function (item, index) {
        const card = document.createElement('article');
        card.className = 'analysis-item';

        const header = document.createElement('div');
        header.className = 'analysis-item-header';

        const rankPill = document.createElement('span');
        rankPill.className = 'pill';
        rankPill.textContent = '#' + String(index + 1);
        header.appendChild(rankPill);

        const scorePill = document.createElement('span');
        scorePill.className = 'pill';
        scorePill.textContent = 'Score: ' + Math.round(Number(item.score || 0) * 100) + '%';
        header.appendChild(scorePill);

        const stylePill = document.createElement('span');
        stylePill.className = 'pill';
        stylePill.textContent = 'Style: ' + labelFromName(item.humor_style || payload.humor_style);
        header.appendChild(stylePill);

        const text = document.createElement('p');
        text.className = 'analysis-item-text';
        text.textContent = item.text || '';

        const why = document.createElement('p');
        why.className = 'analysis-item-why';
        why.textContent = item.why_it_works || 'No rationale returned.';

        card.appendChild(header);
        card.appendChild(text);
        card.appendChild(why);

        const flags = Array.isArray(item.risk_flags) ? item.risk_flags.filter(Boolean) : [];
        if (flags.length) {
          const flagWrap = document.createElement('div');
          flagWrap.className = 'risk-flags';
          flags.forEach(function (flag) {
            const flagNode = document.createElement('span');
            flagNode.className = 'risk-flag';
            flagNode.textContent = flag;
            flagWrap.appendChild(flagNode);
          });
          card.appendChild(flagWrap);
        }

        analysisItems.appendChild(card);
      });
    }

    analysisResultCard.classList.remove('hidden');
  }

  function resetAnalysisResult() {
    analysisDigest.textContent = '';
    analysisDigest.classList.add('hidden');
    analysisItems.innerHTML = '';
    analysisResultCard.classList.add('hidden');
  }

  function syncCustomPromptVisibility() {
    const isCustom = presetSelect.value === 'custom_prompt';
    customPromptField.classList.toggle('hidden', !isCustom);
  }

  async function loadServiceMeta() {
    try {
      const response = await fetch('/health', { method: 'GET' });
      if (!response.ok) {
        throw new Error('health check failed');
      }

      const payload = await response.json();
      const model = payload.model || 'unknown';
      const backend = payload.backend || 'unknown';
      const device = payload.device || 'unknown';
      const analysisModel = payload.analysis_model || 'unknown';

      serviceMetaText.textContent =
        'Service ready • whisper: ' + model + ' • backend: ' + backend + ' • device: ' + device + ' • analysis: ' + analysisModel;
      serviceMetaCard.classList.remove('hidden');
    } catch (_) {
      serviceMetaText.textContent = 'Service status unavailable. You can still try transcribing.';
      serviceMetaCard.classList.remove('hidden');
    }
  }

  async function loadAnalysisMeta() {
    const headers = {};
    const apiKey = apiKeyInput.value.trim();
    if (apiKey) {
      headers['X-Subtext-Key'] = apiKey;
    }

    try {
      const response = await fetch('/analysis/meta', {
        method: 'GET',
        headers: headers,
      });
      if (!response.ok) {
        throw new Error('analysis meta failed');
      }

      analysisMeta = await response.json();

      populateSelect(
        presetSelect,
        (analysisMeta.presets || []).map(function (preset) {
          return { value: preset.name, label: preset.label };
        }),
        'caption_ideas'
      );
      populateSelect(
        styleSelect,
        (analysisMeta.humor_styles || []).map(function (style) {
          return { value: style.name, label: style.label };
        }),
        'dry'
      );
      populateSelect(
        analysisModelSelect,
        (analysisMeta.preferred_models || []).map(function (model) {
          return { value: model, label: model };
        }),
        analysisMeta.default_model || ''
      );
    } catch (_) {
      populateSelect(
        presetSelect,
        [
          { value: 'caption_ideas', label: 'Caption Ideas' },
          { value: 'hook_rewrites', label: 'Hook Rewrites' },
          { value: 'title_pack', label: 'Title Pack' },
          { value: 'custom_prompt', label: 'Custom Prompt' },
        ],
        'caption_ideas'
      );
      populateSelect(
        styleSelect,
        [
          { value: 'dry', label: 'Dry' },
          { value: 'absurd', label: 'Absurd' },
          { value: 'deadpan', label: 'Deadpan' },
          { value: 'brainrot_light', label: 'Brainrot Light' },
          { value: 'wholesome_ironic', label: 'Wholesome Ironic' },
        ],
        'dry'
      );
      populateSelect(
        analysisModelSelect,
        [
          { value: 'gemma3:4b', label: 'gemma3:4b' },
          { value: 'qwen3:8b', label: 'qwen3:8b' },
          { value: 'llama3.1:8b', label: 'llama3.1:8b' },
        ],
        'gemma3:4b'
      );
    }

    syncCustomPromptVisibility();
  }

  apiKeyInput.value = localStorage.getItem(STORAGE_KEY) || '';
  persistKey(apiKeyInput.value);
  loadServiceMeta();
  loadAnalysisMeta();

  apiKeyInput.addEventListener('input', function () {
    persistKey(apiKeyInput.value);
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

  presetSelect.addEventListener('change', syncCustomPromptVisibility);

  form.addEventListener('submit', async function (event) {
    event.preventDefault();
    hideResult();
    resetAnalysisResult();
    finalizeTranscript();

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
    showStreamIndicator('Transcribing...');
    showResult({ text: '', duration: 0, latency: 0 }, true);

    try {
      const response = await fetch('/transcribe/stream', {
        method: 'POST',
        headers: headers,
        body: formData,
      });

      if (!response.ok) {
        let detail = 'Request failed.';
        try {
          const json = await response.json();
          detail = json.detail || detail;
        } catch (_) {}
        throw new Error(detail);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let finalPayload = {};

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Process complete events in buffer
        while (true) {
          const eventEnd = buffer.indexOf('\n\n');
          if (eventEnd === -1) break;

          const rawEvent = buffer.slice(0, eventEnd);
          buffer = buffer.slice(eventEnd + 2);

          const lines = rawEvent.split('\n');
          let eventType = '';
          let eventData = '';

          for (const line of lines) {
            if (line.startsWith('event: ')) {
              eventType = line.slice(7).trim();
            } else if (line.startsWith('data: ')) {
              eventData = line.slice(6);
            }
          }

          let parsedData = eventData;
          if (eventData) {
            try {
              parsedData = JSON.parse(eventData);
            } catch (_) {}
          }

          if (eventType === 'chunk') {
            appendTranscriptChunk(parsedData.text || '');
          } else if (eventType === 'done') {
            if (parsedData && typeof parsedData === 'object') {
              finalPayload = parsedData;
            }
          } else if (eventType === 'error') {
            throw new Error((parsedData && parsedData.detail) || 'Stream error.');
          } else if (eventType === 'progress') {
            hideStatus();
            showStreamIndicator(parsedData.message || 'Transcribing...');
          }
        }
      }

      hideStatus();
      hideStreamIndicator();
      finalizeTranscript();

      const finalText = transcriptOutput.value;
      showResult({ text: finalText, ...finalPayload }, false);
    } catch (error) {
      hideStatus();
      hideStreamIndicator();
      finalizeTranscript();
      showStatus(error.message || 'Transcription failed.');
    } finally {
      setBusy(false);
    }
  });

  downloadBtn.addEventListener('click', async function () {
    hideResult();

    const url = urlInput.value.trim();
    const file = fileInput.files[0] || null;
    if (!url) {
      showStatus('Paste a media URL to download.');
      return;
    }

    if (file) {
      showStatus('Download mode uses a URL only. Clear the file first.');
      return;
    }

    const key = apiKeyInput.value.trim();
    if (!key) {
      showStatus('Enter the shared key first.');
      return;
    }

    persistKey(key);
    showStatus('Preparing download...');
    setBusy(true);

    try {
      const body = new URLSearchParams();
      body.set('url', url);

      const response = await fetch('/download-video', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'X-Subtext-Key': key,
        },
        body: body.toString(),
      });

      if (!response.ok) {
        const payload = await response.json().catch(function () {
          return { detail: 'Download failed.' };
        });
        throw new Error(payload.detail || 'Download failed.');
      }

      showStatus('Downloading...');
      const blob = await response.blob();
      const name = filenameFromContentDisposition(response.headers.get('Content-Disposition'));

      const objectUrl = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = name;
      anchor.style.display = 'none';
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      window.URL.revokeObjectURL(objectUrl);

      showStatus('Download complete.');
      window.setTimeout(function () {
        hideStatus();
      }, 4000);
    } catch (error) {
      showStatus(error.message || 'Download failed.');
    } finally {
      setBusy(false);
    }
  });

  analyzeBtn.addEventListener('click', async function () {
    const transcript = transcriptOutput.value.trim();
    if (!transcript) {
      showStatus('Transcribe something first.');
      return;
    }

    if (presetSelect.value === 'custom_prompt' && !customPromptInput.value.trim()) {
      showStatus('Enter a custom prompt first.');
      return;
    }

    const headers = { 'Content-Type': 'application/json' };
    const apiKey = apiKeyInput.value.trim();
    if (apiKey) {
      headers['X-Subtext-Key'] = apiKey;
    }

    setAnalyzeBusy(true);
    showStatus('Running transcript analysis...');

    try {
      const response = await fetch('/analyze', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({
          transcript: transcript,
          preset: presetSelect.value,
          humor_style: styleSelect.value,
          model: analysisModelSelect.value || null,
          custom_prompt: customPromptInput.value.trim(),
        }),
      });

      if (!response.ok) {
        const payload = await response.json().catch(function () {
          return { detail: 'Analysis request failed.' };
        });
        throw new Error(payload.detail || 'Analysis request failed.');
      }

      const payload = await response.json();
      renderAnalysisResult(payload);
      hideStatus();
    } catch (error) {
      showStatus(error.message || 'Analysis failed.');
    } finally {
      setAnalyzeBusy(false);
    }
  });

  clearAnalysisBtn.addEventListener('click', function () {
    resetAnalysisResult();
    customPromptInput.value = '';
    hideStatus();
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

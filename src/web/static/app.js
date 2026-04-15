/* Subtext Web — main application logic */
(function () {
  'use strict';

  const STORAGE_KEY = 'subtext-key';

  // ─── State ────────────────────────────────────────────────────────────────
  const state = {
    apiKey: '',
    activePage: 'media',
    transcript: '',            // last completed transcript
    chatMessages: [],          // [{role, content}, …]
    chatContext: null,         // transcript string injected as context (or null)
    chatContextLabel: '',
    chatModel: '',
    chatStreaming: false,
    analysisMeta: {
      default_model: '',
      preferred_models: [],
      available_models: [],
      presets: [],
      humor_styles: [],
    },
    // Reference to the DOM bubble currently being streamed into
    _streamBubble: null,
    _streamCursor: null,
  };

  // ─── DOM refs ─────────────────────────────────────────────────────────────
  const $ = (id) => document.getElementById(id);

  const serviceDot          = $('service-dot');
  const serviceNotice       = $('service-notice');
  const serviceNoticeText   = $('service-notice-text');
  const keyToggleBtn        = $('key-toggle-btn');
  const keyDrawer           = $('key-drawer');
  const apiKeyInput         = $('api-key');
  const keySaveBtn          = $('key-save-btn');

  // Media page
  const transcribeForm      = $('transcribe-form');
  const urlInput            = $('url-input');
  const fileInput           = $('file-input');
  const filePickLabel       = $('file-pick-label');
  const filePickText        = $('file-pick-text');
  const submitBtn           = $('submit-btn');
  const downloadBtn         = $('download-btn');
  const statusCard          = $('status-card');
  const statusText          = $('status-text');
  const resultCard          = $('result-card');
  const transcriptOutput    = $('transcript-output');
  const durationPill        = $('duration-pill');
  const latencyPill         = $('latency-pill');
  const streamStatusPill    = $('stream-status-pill');
  const streamingCursor     = $('streaming-cursor');
  const streamIndicator     = $('stream-indicator');
  const streamLabel         = $('stream-label');
  const copyBtn             = $('copy-btn');
  const chatCtxBtn          = $('chat-ctx-btn');
  const analysisCard        = $('analysis-card');
  const analysisResultCard  = $('analysis-result-card');
  const presetSelect        = $('preset-select');
  const styleSelect         = $('style-select');
  const analysisModelSelect = $('analysis-model-select');
  const customPromptField   = $('custom-prompt-field');
  const customPromptInput   = $('custom-prompt-input');
  const analyzeBtn          = $('analyze-btn');
  const clearAnalysisBtn    = $('clear-analysis-btn');
  const analysisMetaPill    = $('analysis-meta-pill');
  const analysisDigest      = $('analysis-digest');
  const analysisItems       = $('analysis-items');

  // Chat page
  const chatModelSelect     = $('chat-model-select');
  const chatModelsRefresh   = $('chat-models-refresh');
  const clearChatBtn        = $('clear-chat-btn');
  const contextBar          = $('context-bar');
  const contextLabel        = $('context-label');
  const clearContextBtn     = $('clear-context-btn');
  const messagesEl          = $('messages');
  const welcomeMsg          = $('welcome-msg');
  const chatInput           = $('chat-input');
  const sendBtn             = $('send-btn');
  const stopBtn             = $('stop-btn');

  // Nav
  const navMedia            = $('nav-media');
  const navChat             = $('nav-chat');

  // ─── Utilities ────────────────────────────────────────────────────────────

  function apiHeaders(extra) {
    var h = Object.assign({}, extra || {});
    if (state.apiKey) h['X-Subtext-Key'] = state.apiKey;
    return h;
  }

  function persistKey(value) {
    state.apiKey = (value || '').trim();
    localStorage.setItem(STORAGE_KEY, state.apiKey);
    var enc = encodeURIComponent(state.apiKey);
    if (state.apiKey) {
      document.cookie = 'subtext_key=' + enc + '; path=/; max-age=31536000; samesite=lax';
    } else {
      document.cookie = 'subtext_key=; path=/; max-age=0; samesite=lax';
    }
  }

  function filenameFromCD(header) {
    if (!header) return 'download';
    var m = /filename\*=UTF-8''([^;\n]+)/i.exec(header);
    if (m) { try { return decodeURIComponent(m[1].trim().replace(/^["']|["']$/g, '')); } catch (_) {} }
    m = /filename="([^"]+)"/i.exec(header);
    if (m) return m[1];
    m = /filename=([^;\s]+)/i.exec(header);
    if (m) return m[1].trim().replace(/^["']|["']$/g, '');
    return 'download';
  }

  function labelFromName(name) {
    return String(name || '').split('_').map(function (p) {
      return p ? p.charAt(0).toUpperCase() + p.slice(1) : '';
    }).join(' ');
  }

  function populateSelect(sel, items, fallback) {
    sel.innerHTML = '';
    items.forEach(function (item) {
      var opt = document.createElement('option');
      opt.value = item.value;
      opt.textContent = item.label;
      sel.appendChild(opt);
    });
    if (fallback) sel.value = fallback;
    if (!sel.value && items.length) sel.value = items[0].value;
  }

  // Auto-grow the chat textarea
  function autoGrow(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 130) + 'px';
  }

  function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  // ─── Navigation ───────────────────────────────────────────────────────────

  function switchPage(page) {
    state.activePage = page;

    document.querySelectorAll('.page').forEach(function (el) {
      el.classList.remove('active');
      el.setAttribute('aria-hidden', 'true');
    });

    var target = document.getElementById('page-' + page);
    if (target) {
      target.classList.add('active');
      target.removeAttribute('aria-hidden');
    }

    [navMedia, navChat].forEach(function (btn) {
      var active = btn.dataset.page === page;
      btn.classList.toggle('active', active);
      btn.setAttribute('aria-current', active ? 'page' : 'false');
    });

    if (page === 'chat') {
      chatInput.focus();
      scrollToBottom();
    }
  }

  navMedia.addEventListener('click', function () { switchPage('media'); });
  navChat.addEventListener('click', function () { switchPage('chat'); });

  // ─── Key drawer ───────────────────────────────────────────────────────────

  keyToggleBtn.addEventListener('click', function () {
    var open = keyDrawer.classList.toggle('open');
    keyToggleBtn.classList.toggle('active', open);
    keyDrawer.setAttribute('aria-hidden', open ? 'false' : 'true');
    if (open) apiKeyInput.focus();
  });

  function saveKey() {
    persistKey(apiKeyInput.value);
    keyDrawer.classList.remove('open');
    keyToggleBtn.classList.remove('active');
    keyDrawer.setAttribute('aria-hidden', 'true');
    keyToggleBtn.classList.toggle('active', !!state.apiKey);
  }

  keySaveBtn.addEventListener('click', saveKey);
  apiKeyInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); saveKey(); }
  });

  // ─── Service health ───────────────────────────────────────────────────────

  async function loadServiceHealth() {
    try {
      var res = await fetch('/health');
      if (!res.ok) throw new Error('bad status');
      var data = await res.json();
      serviceDot.classList.add('ok');
      serviceDot.title = 'Service ready · whisper: ' + data.model + ' · ' + data.backend;
      serviceNoticeText.textContent =
        'Ready · whisper: ' + data.model + ' · ' + data.backend + ' · ' + data.device;
      serviceNotice.classList.remove('hidden');
    } catch (_) {
      serviceDot.classList.add('error');
      serviceDot.title = 'Service unreachable';
    }
  }

  // ─── Analysis meta ────────────────────────────────────────────────────────

  async function loadAnalysisMeta() {
    try {
      var res = await fetch('/analysis/meta', { headers: apiHeaders() });
      if (!res.ok) throw new Error();
      state.analysisMeta = await res.json();
    } catch (_) {
      state.analysisMeta = {
        default_model: 'gemma3:4b',
        preferred_models: ['gemma3:4b', 'qwen3:8b', 'llama3.1:8b'],
        available_models: [],
        presets: [
          { name: 'caption_ideas', label: 'Caption Ideas' },
          { name: 'hook_rewrites', label: 'Hook Rewrites' },
          { name: 'title_pack',    label: 'Title Pack' },
          { name: 'custom_prompt', label: 'Custom Prompt' },
        ],
        humor_styles: [
          { name: 'dry',              label: 'Dry' },
          { name: 'absurd',           label: 'Absurd' },
          { name: 'deadpan',          label: 'Deadpan' },
          { name: 'brainrot_light',   label: 'Brainrot Light' },
          { name: 'wholesome_ironic', label: 'Wholesome Ironic' },
        ],
      };
    }

    var meta = state.analysisMeta;
    populateSelect(presetSelect, meta.presets.map(function (p) {
      return { value: p.name, label: p.label };
    }), 'caption_ideas');
    populateSelect(styleSelect, meta.humor_styles.map(function (s) {
      return { value: s.name, label: s.label };
    }), 'dry');
    populateSelect(analysisModelSelect, meta.preferred_models.map(function (m) {
      return { value: m, label: m };
    }), meta.default_model || '');

    syncCustomPromptVisibility();
  }

  function syncCustomPromptVisibility() {
    customPromptField.classList.toggle('hidden', presetSelect.value !== 'custom_prompt');
  }
  presetSelect.addEventListener('change', syncCustomPromptVisibility);

  // ─── Chat models ──────────────────────────────────────────────────────────

  async function loadChatModels() {
    try {
      var res = await fetch('/chat/models', { headers: apiHeaders() });
      if (!res.ok) throw new Error();
      var data = await res.json();
      var models = data.models || [];
      var def = data.default || '';
      populateSelect(chatModelSelect, models.map(function (m) {
        return { value: m, label: m };
      }), def);
      if (chatModelSelect.value) state.chatModel = chatModelSelect.value;
    } catch (_) {
      // Fallback populated inline
      populateSelect(chatModelSelect, [
        { value: 'gemma3:4b',   label: 'gemma3:4b' },
        { value: 'qwen3:8b',    label: 'qwen3:8b' },
        { value: 'llama3.1:8b', label: 'llama3.1:8b' },
      ], 'gemma3:4b');
    }
    state.chatModel = chatModelSelect.value;
  }

  chatModelSelect.addEventListener('change', function () {
    state.chatModel = chatModelSelect.value;
  });
  chatModelsRefresh.addEventListener('click', loadChatModels);

  // ─── Media: transcription ─────────────────────────────────────────────────

  urlInput.addEventListener('input', function () {
    if (urlInput.value.trim()) { fileInput.value = ''; filePickText.textContent = 'Choose audio or video…'; filePickLabel.classList.remove('has-file'); }
  });

  fileInput.addEventListener('change', function () {
    if (fileInput.files.length) {
      urlInput.value = '';
      filePickText.textContent = fileInput.files[0].name;
      filePickLabel.classList.add('has-file');
    }
  });

  function setMediaBusy(busy) {
    submitBtn.disabled = busy;
    downloadBtn.disabled = busy;
  }

  function showStatus(msg) {
    statusText.textContent = msg;
    statusCard.classList.remove('hidden');
  }
  function hideStatus() { statusCard.classList.add('hidden'); }

  function showStreamIndicator(msg) {
    streamLabel.textContent = msg || 'Transcribing…';
    streamIndicator.classList.remove('hidden');
  }
  function hideStreamIndicator() { streamIndicator.classList.add('hidden'); }

  transcribeForm.addEventListener('submit', async function (e) {
    e.preventDefault();
    var url  = urlInput.value.trim();
    var file = fileInput.files[0] || null;

    if (!url && !file) { showStatus('Paste a URL or choose a file.'); return; }
    if (url && file)   { showStatus('Use a URL or a file — not both.'); return; }

    resultCard.classList.add('hidden');
    analysisCard.classList.add('hidden');
    analysisResultCard.classList.add('hidden');
    streamStatusPill.classList.add('hidden');
    streamingCursor.classList.add('hidden');
    state.transcript = '';

    var fd = new FormData();
    if (url)  fd.append('url',  url);
    if (file) fd.append('file', file);

    setMediaBusy(true);
    showStatus(url ? 'Downloading and transcribing…' : 'Uploading and transcribing…');
    showStreamIndicator('Transcribing…');
    transcriptOutput.value = '';
    resultCard.classList.remove('hidden');
    streamStatusPill.classList.remove('hidden');
    streamingCursor.classList.remove('hidden');
    durationPill.textContent = '—';
    latencyPill.textContent  = '—';

    try {
      var res = await fetch('/transcribe/stream', {
        method: 'POST',
        headers: apiHeaders(),
        body: fd,
      });

      if (!res.ok) {
        var errJson = await res.json().catch(function () { return {}; });
        throw new Error(errJson.detail || 'Request failed.');
      }

      var reader  = res.body.getReader();
      var decoder = new TextDecoder();
      var buffer  = '';
      var finalPayload = {};

      while (true) {
        var chunk = await reader.read();
        if (chunk.done) break;
        buffer += decoder.decode(chunk.value, { stream: true });

        while (true) {
          var end = buffer.indexOf('\n\n');
          if (end === -1) break;
          var rawEvent = buffer.slice(0, end);
          buffer = buffer.slice(end + 2);

          var lines = rawEvent.split('\n');
          var evtType = '', evtData = '';
          lines.forEach(function (l) {
            if (l.startsWith('event: ')) evtType = l.slice(7).trim();
            if (l.startsWith('data: '))  evtData = l.slice(6);
          });

          var parsed = evtData;
          try { parsed = JSON.parse(evtData); } catch (_) {}

          if (evtType === 'chunk') {
            transcriptOutput.value += (parsed.text || '');
            transcriptOutput.scrollTop = transcriptOutput.scrollHeight;
          } else if (evtType === 'done') {
            if (parsed && typeof parsed === 'object') finalPayload = parsed;
          } else if (evtType === 'error') {
            throw new Error((parsed && parsed.detail) || 'Stream error.');
          } else if (evtType === 'progress') {
            hideStatus();
            showStreamIndicator(parsed.message || 'Transcribing…');
          }
        }
      }

      state.transcript = transcriptOutput.value;
      durationPill.textContent = 'Duration: ' + Number(finalPayload.duration || 0).toFixed(2) + 's';
      latencyPill.textContent  = 'Latency: '  + Number(finalPayload.latency  || 0).toFixed(2) + 's';
      hideStatus();
      hideStreamIndicator();
      streamStatusPill.classList.add('hidden');
      streamingCursor.classList.add('hidden');

      if (state.transcript.trim()) analysisCard.classList.remove('hidden');

    } catch (err) {
      hideStatus();
      hideStreamIndicator();
      streamStatusPill.classList.add('hidden');
      streamingCursor.classList.add('hidden');
      showStatus(err.message || 'Transcription failed.');
    } finally {
      setMediaBusy(false);
    }
  });

  // ─── Media: download video ─────────────────────────────────────────────────

  downloadBtn.addEventListener('click', async function () {
    var url = urlInput.value.trim();
    if (!url) { showStatus('Paste a media URL to download.'); return; }
    if (!state.apiKey) { showStatus('Enter the shared key first.'); return; }

    setMediaBusy(true);
    showStatus('Preparing download…');

    try {
      var body = new URLSearchParams();
      body.set('url', url);

      var res = await fetch('/download-video', {
        method: 'POST',
        headers: apiHeaders({ 'Content-Type': 'application/x-www-form-urlencoded' }),
        body: body.toString(),
      });

      if (!res.ok) {
        var data = await res.json().catch(function () { return {}; });
        throw new Error(data.detail || 'Download failed.');
      }

      showStatus('Saving…');
      var blob = await res.blob();
      var name = filenameFromCD(res.headers.get('Content-Disposition'));
      var objUrl = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = objUrl; a.download = name; a.style.display = 'none';
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      URL.revokeObjectURL(objUrl);

      showStatus('Download complete.');
      setTimeout(hideStatus, 4000);
    } catch (err) {
      showStatus(err.message || 'Download failed.');
    } finally {
      setMediaBusy(false);
    }
  });

  // ─── Media: copy transcript ────────────────────────────────────────────────

  copyBtn.addEventListener('click', function () {
    var text = transcriptOutput.value;
    if (!text) return;
    var original = copyBtn.textContent;
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(function () {
        copyBtn.textContent = 'Copied';
        setTimeout(function () { copyBtn.textContent = original; }, 1600);
      });
    } else {
      transcriptOutput.removeAttribute('readonly');
      transcriptOutput.select();
      document.execCommand('copy');
      transcriptOutput.setAttribute('readonly', '');
      copyBtn.textContent = 'Copied';
      setTimeout(function () { copyBtn.textContent = original; }, 1600);
    }
  });

  // ─── Media: "Chat about this" ──────────────────────────────────────────────

  chatCtxBtn.addEventListener('click', function () {
    if (!state.transcript) return;
    setChatContext(state.transcript, 'transcript');
    switchPage('chat');
  });

  // ─── Media: analysis ──────────────────────────────────────────────────────

  function setAnalyzeBusy(busy) {
    analyzeBtn.disabled = busy;
    clearAnalysisBtn.disabled = busy;
    presetSelect.disabled = busy;
    styleSelect.disabled = busy;
    analysisModelSelect.disabled = busy;
  }

  analyzeBtn.addEventListener('click', async function () {
    var transcript = transcriptOutput.value.trim();
    if (!transcript) { showStatus('Transcribe something first.'); return; }
    if (presetSelect.value === 'custom_prompt' && !customPromptInput.value.trim()) {
      showStatus('Enter a custom prompt.'); return;
    }

    setAnalyzeBusy(true);
    showStatus('Running analysis…');

    try {
      var res = await fetch('/analyze', {
        method: 'POST',
        headers: apiHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          transcript:    transcript,
          preset:        presetSelect.value,
          humor_style:   styleSelect.value,
          model:         analysisModelSelect.value || null,
          custom_prompt: customPromptInput.value.trim(),
        }),
      });

      if (!res.ok) {
        var data = await res.json().catch(function () { return {}; });
        throw new Error(data.detail || 'Analysis failed.');
      }

      renderAnalysis(await res.json());
      hideStatus();
    } catch (err) {
      showStatus(err.message || 'Analysis failed.');
    } finally {
      setAnalyzeBusy(false);
    }
  });

  clearAnalysisBtn.addEventListener('click', function () {
    analysisDigest.textContent = '';
    analysisDigest.classList.add('hidden');
    analysisItems.innerHTML = '';
    analysisResultCard.classList.add('hidden');
    customPromptInput.value = '';
    hideStatus();
  });

  function renderAnalysis(payload) {
    analysisItems.innerHTML = '';
    analysisMetaPill.textContent =
      labelFromName(payload.preset) + ' · ' +
      labelFromName(payload.humor_style) + ' · ' +
      (payload.model || '—');

    if (payload.digest) {
      analysisDigest.textContent = payload.digest;
      analysisDigest.classList.remove('hidden');
    } else {
      analysisDigest.classList.add('hidden');
    }

    var items = Array.isArray(payload.items) ? payload.items : [];

    if (payload.custom_response) {
      var art = document.createElement('article');
      art.className = 'analysis-item';
      var prompt = document.createElement('p');
      prompt.className = 'analysis-item-why';
      prompt.textContent = 'Prompt: ' + (payload.custom_prompt || 'Custom');
      var text = document.createElement('p');
      text.className = 'analysis-item-text';
      text.textContent = payload.custom_response;
      art.appendChild(prompt); art.appendChild(text);
      analysisItems.appendChild(art);
    } else if (!items.length) {
      var empty = document.createElement('p');
      empty.className = 'analysis-item-why';
      empty.textContent = 'No ideas returned.';
      analysisItems.appendChild(empty);
    } else {
      items.forEach(function (item, idx) {
        var art = document.createElement('article');
        art.className = 'analysis-item';

        var hdr = document.createElement('div');
        hdr.className = 'analysis-item-header';

        function mkPill(txt) {
          var s = document.createElement('span'); s.className = 'pill'; s.textContent = txt; return s;
        }
        hdr.appendChild(mkPill('#' + (idx + 1)));
        hdr.appendChild(mkPill('Score: ' + Math.round(Number(item.score || 0) * 100) + '%'));
        hdr.appendChild(mkPill(labelFromName(item.humor_style || payload.humor_style)));

        var txt = document.createElement('p');
        txt.className = 'analysis-item-text';
        txt.textContent = item.text || '';

        var why = document.createElement('p');
        why.className = 'analysis-item-why';
        why.textContent = item.why_it_works || '';

        art.appendChild(hdr); art.appendChild(txt); art.appendChild(why);

        var flags = Array.isArray(item.risk_flags) ? item.risk_flags.filter(Boolean) : [];
        if (flags.length) {
          var fw = document.createElement('div'); fw.className = 'risk-flags';
          flags.forEach(function (f) {
            var s = document.createElement('span'); s.className = 'risk-flag'; s.textContent = f; fw.appendChild(s);
          });
          art.appendChild(fw);
        }

        analysisItems.appendChild(art);
      });
    }

    analysisResultCard.classList.remove('hidden');
  }

  // ─── Chat: context ─────────────────────────────────────────────────────────

  function setChatContext(text, label) {
    state.chatContext = text;
    state.chatContextLabel = label || 'transcript';
    contextLabel.textContent = 'Context: ' + (state.chatContextLabel.length > 36
      ? state.chatContextLabel.slice(0, 33) + '…'
      : state.chatContextLabel);
    contextBar.classList.remove('hidden');
  }

  function clearChatContext() {
    state.chatContext = null;
    state.chatContextLabel = '';
    contextBar.classList.add('hidden');
  }

  clearContextBtn.addEventListener('click', clearChatContext);

  // ─── Chat: message rendering ───────────────────────────────────────────────

  function hideWelcome() {
    if (welcomeMsg) welcomeMsg.style.display = 'none';
  }

  function appendMessage(role, content) {
    hideWelcome();
    var msg = document.createElement('div');
    msg.className = 'msg ' + role;

    var lbl = document.createElement('div');
    lbl.className = 'msg-label';
    lbl.textContent = role === 'user' ? 'You' : 'Assistant';

    var bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.textContent = content;

    msg.appendChild(lbl);
    msg.appendChild(bubble);
    messagesEl.appendChild(msg);
    scrollToBottom();
    return bubble;
  }

  function appendErrorMsg(text) {
    hideWelcome();
    var div = document.createElement('div');
    div.className = 'msg-error';
    div.textContent = text;
    messagesEl.appendChild(div);
    scrollToBottom();
  }

  // Begin a streaming assistant bubble — returns the bubble element
  function beginStreamBubble() {
    hideWelcome();
    var msg = document.createElement('div');
    msg.className = 'msg assistant';

    var lbl = document.createElement('div');
    lbl.className = 'msg-label';
    lbl.textContent = 'Assistant';

    var bubble = document.createElement('div');
    bubble.className = 'bubble';

    var cursor = document.createElement('span');
    cursor.className = 'typing-cursor';
    bubble.appendChild(cursor);

    msg.appendChild(lbl);
    msg.appendChild(bubble);
    messagesEl.appendChild(msg);
    scrollToBottom();

    state._streamBubble = bubble;
    state._streamCursor = cursor;
    return bubble;
  }

  function appendToken(token) {
    if (!state._streamBubble || !state._streamCursor) return;
    // Insert text node before the cursor
    var textNode = document.createTextNode(token);
    state._streamBubble.insertBefore(textNode, state._streamCursor);
    scrollToBottom();
  }

  function finalizeStream(fullText) {
    if (state._streamBubble && state._streamCursor) {
      state._streamCursor.remove();
      state._streamCursor = null;
      // Store complete content on the bubble for later reference
      state._streamBubble.dataset.content = fullText;
    }
    state._streamBubble = null;
  }

  // ─── Chat: send / stream ────────────────────────────────────────────────────

  function setChatBusy(busy) {
    state.chatStreaming = busy;
    chatInput.disabled = busy;
    sendBtn.classList.toggle('hidden', busy);
    stopBtn.classList.toggle('hidden', !busy);
  }

  async function sendChat() {
    var text = chatInput.value.trim();
    if (!text || state.chatStreaming) return;

    var model = chatModelSelect.value || state.chatModel;
    if (!model) { appendErrorMsg('Select a model first.'); return; }

    // Show user message
    appendMessage('user', text);
    state.chatMessages.push({ role: 'user', content: text });
    chatInput.value = '';
    autoGrow(chatInput);

    setChatBusy(true);

    var requestBody = {
      message:  text,
      history:  state.chatMessages.slice(0, -1),  // history before this message
      model:    model,
    };
    if (state.chatContext) {
      requestBody.transcript_context = state.chatContext;
    }

    var fullResponse = '';
    beginStreamBubble();

    try {
      var res = await fetch('/chat/stream', {
        method: 'POST',
        headers: apiHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(requestBody),
      });

      if (!res.ok) {
        var errData = await res.json().catch(function () { return {}; });
        throw new Error(errData.detail || 'Chat request failed.');
      }

      var reader  = res.body.getReader();
      var decoder = new TextDecoder();
      var buffer  = '';

      while (true) {
        var chunk = await reader.read();
        if (chunk.done) break;
        buffer += decoder.decode(chunk.value, { stream: true });

        while (true) {
          var end = buffer.indexOf('\n\n');
          if (end === -1) break;
          var rawEvent = buffer.slice(0, end);
          buffer = buffer.slice(end + 2);

          var lines = rawEvent.split('\n');
          var evtType = '', evtData = '';
          lines.forEach(function (l) {
            if (l.startsWith('event: ')) evtType = l.slice(7).trim();
            if (l.startsWith('data: '))  evtData = l.slice(6);
          });

          var parsed = evtData;
          try { parsed = JSON.parse(evtData); } catch (_) {}

          if (evtType === 'token') {
            var tok = (parsed && parsed.text) || '';
            fullResponse += tok;
            appendToken(tok);
          } else if (evtType === 'done') {
            // stream finished normally
          } else if (evtType === 'error') {
            throw new Error((parsed && parsed.detail) || 'Stream error.');
          }
        }
      }

      finalizeStream(fullResponse);
      state.chatMessages.push({ role: 'assistant', content: fullResponse });

    } catch (err) {
      finalizeStream('');
      appendErrorMsg(err.message || 'Something went wrong.');
      // Roll back the user message we added optimistically
      state.chatMessages.pop();
    } finally {
      setChatBusy(false);
      chatInput.focus();
    }
  }

  sendBtn.addEventListener('click', sendChat);

  stopBtn.addEventListener('click', function () {
    // Abort is handled by the reader going out of scope on next request;
    // for a hard stop we mark busy=false so the loop's finally runs cleanly.
    setChatBusy(false);
    finalizeStream(state._streamBubble
      ? (state._streamBubble.textContent || '')
      : '');
  });

  chatInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendChat();
    }
  });

  chatInput.addEventListener('input', function () { autoGrow(chatInput); });

  clearChatBtn.addEventListener('click', function () {
    state.chatMessages = [];
    messagesEl.innerHTML = '';
    // Restore welcome message
    var welcome = document.createElement('div');
    welcome.className = 'welcome-msg';
    welcome.id = 'welcome-msg';
    welcome.innerHTML =
      '<p class="welcome-title">Subtext Chat</p>' +
      '<p class="welcome-body">Chat with a local model. Transcribe something on the Media tab, ' +
      'then tap <strong>Chat about this →</strong> to ask questions about it.</p>';
    messagesEl.appendChild(welcome);
  });

  // ─── Boot ─────────────────────────────────────────────────────────────────

  function init() {
    // Restore key from storage
    var stored = localStorage.getItem(STORAGE_KEY) || '';
    apiKeyInput.value = stored;
    persistKey(stored);
    // Show key icon as active if key exists
    keyToggleBtn.classList.toggle('active', !!stored);

    loadServiceHealth();
    loadAnalysisMeta();
    loadChatModels();
  }

  init();

})();

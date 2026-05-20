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
    currentThreadId: null,     // active thread (null = not yet persisted)
    transcribeBusy: false,
    _transcribeAbort: null,    // AbortController for the active transcribe fetch
    _chatAbort: null,          // AbortController for the active chat fetch
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
  const downloadAudioBtn    = $('download-audio-btn');
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
  const downloadTxtBtn      = $('download-txt-btn');
  const chatCtxBtn          = $('chat-ctx-btn');

  // Chat page
  const chatModelSelect     = $('chat-model-select');
  const chatModelsRefresh   = $('chat-models-refresh');
  const clearChatBtn        = $('clear-chat-btn');
  const threadsBtn          = $('threads-btn');
  const attachCtxBtn        = $('attach-ctx-btn');
  const contextBar          = $('context-bar');
  const contextLabel        = $('context-label');
  const clearContextBtn     = $('clear-context-btn');
  const messagesEl          = $('messages');
  const welcomeMsg          = $('welcome-msg');
  const quickActions        = $('quick-actions');
  const chatInput           = $('chat-input');
  const sendBtn             = $('send-btn');
  const stopBtn             = $('stop-btn');

  // Threads sheet
  const threadsSheet        = $('threads-sheet');
  const threadsBackdrop     = $('threads-backdrop');
  const threadsCloseBtn     = $('threads-close-btn');
  const threadsSheetTitle   = $('threads-sheet-title');
  const threadList          = $('thread-list');
  const threadsEmpty        = $('threads-empty');

  // Models sheet
  const modelsBtn           = $('models-btn');
  const modelsSheet         = $('models-sheet');
  const modelsBackdrop      = $('models-backdrop');
  const modelsCloseBtn      = $('models-close-btn');
  const modelsRefreshBtn    = $('models-refresh-btn');
  const modelsBody          = $('models-body');

  // Attach context sheet
  const attachSheet         = $('attach-sheet');
  const attachBackdrop      = $('attach-backdrop');
  const attachCloseBtn      = $('attach-close-btn');
  const attachChoices       = $('attach-choices');
  const attachPaste         = $('attach-paste');
  const attachBackBtn       = $('attach-back-btn');
  const attachText          = $('attach-text');
  const attachFile          = $('attach-file');
  const attachImage         = $('attach-image');
  const attachChoicePaste   = $('attach-choice-paste');
  const attachApplyBtn      = $('attach-apply-btn');

  // Toast
  const toastEl             = $('toast');

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
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
  }

  function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  // ─── Toast ────────────────────────────────────────────────────────────────
  let _toastTimer = null;
  function toast(msg, ms) {
    if (!toastEl) return;
    if (_toastTimer) { clearTimeout(_toastTimer); _toastTimer = null; }
    toastEl.textContent = msg;
    toastEl.classList.remove('hidden');
    // Force reflow so the transition runs each time.
    void toastEl.offsetWidth;
    toastEl.classList.add('show');
    _toastTimer = setTimeout(function () {
      toastEl.classList.remove('show');
      _toastTimer = setTimeout(function () {
        toastEl.classList.add('hidden');
      }, 220);
    }, ms || 1400);
  }

  // ─── Clipboard (iOS-safe, works over HTTP without secureContext) ─────────
  function copyToClipboard(text) {
    // Prefer the modern API when we actually have it.
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      // iOS Safari needs a focused, selectable, non-readonly element. Use a
      // throwaway textarea so we don't disturb the real transcript view.
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');         // hint, but iOS still needs setSelectionRange
      ta.contentEditable = 'true';             // required for iOS programmatic copy
      ta.style.position = 'fixed';
      ta.style.top = '0';
      ta.style.left = '0';
      ta.style.opacity = '0';
      ta.style.pointerEvents = 'none';
      document.body.appendChild(ta);
      try {
        ta.focus();
        var isIOS = /iP(hone|od|ad)/.test(navigator.userAgent);
        if (isIOS) {
          var range = document.createRange();
          range.selectNodeContents(ta);
          var sel = window.getSelection();
          sel.removeAllRanges();
          sel.addRange(range);
          ta.setSelectionRange(0, text.length);
        } else {
          ta.select();
        }
        var ok = document.execCommand('copy');
        if (ok) resolve(); else reject(new Error('execCommand returned false'));
      } catch (err) {
        reject(err);
      } finally {
        document.body.removeChild(ta);
      }
    });
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

  // ─── Chat models ──────────────────────────────────────────────────────────

  const PROVIDER_LABELS = { ollama: 'Ollama', lmstudio: 'LM Studio' };

  function renderChatModelOptions(models, def) {
    chatModelSelect.innerHTML = '';

    if (!models.length) {
      var opt = document.createElement('option');
      opt.value = '';
      opt.textContent = 'No models — start Ollama or LM Studio';
      opt.disabled = true;
      chatModelSelect.appendChild(opt);
      return;
    }

    // Group by provider so iOS Safari renders them in optgroup buckets.
    var byProvider = {};
    models.forEach(function (m) {
      if (!byProvider[m.provider]) byProvider[m.provider] = [];
      byProvider[m.provider].push(m);
    });

    var providers = Object.keys(byProvider).sort();
    providers.forEach(function (prov) {
      var group = document.createElement('optgroup');
      group.label = PROVIDER_LABELS[prov] || prov;
      byProvider[prov].forEach(function (m) {
        var opt = document.createElement('option');
        opt.value = m.id;     // "ollama:qwen3:8b"
        opt.textContent = (m.loaded ? '● ' : '') + m.name;
        group.appendChild(opt);
      });
      chatModelSelect.appendChild(group);
    });

    if (def) chatModelSelect.value = def;
    // If the default isn't a real option (e.g. providers list changed), pick the
    // first selectable option instead so the select doesn't show blank.
    if (!chatModelSelect.value) {
      var first = chatModelSelect.querySelector('option:not([disabled])');
      if (first) chatModelSelect.value = first.value;
    }
  }

  async function loadChatModels() {
    try {
      var res = await fetch('/chat/models', { headers: apiHeaders() });
      if (!res.ok) throw new Error();
      var data = await res.json();
      renderChatModelOptions(data.models || [], data.default || '');
    } catch (_) {
      renderChatModelOptions([], '');
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
    state.transcribeBusy = !!busy;
    submitBtn.disabled = busy;
    downloadAudioBtn.disabled = busy;
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

  // Single source of truth for clearing the transcribe panel between runs.
  function resetTranscribePanel(keepResultVisible) {
    if (!keepResultVisible) resultCard.classList.add('hidden');
    streamStatusPill.classList.add('hidden');
    streamingCursor.classList.add('hidden');
    hideStreamIndicator();
    hideStatus();
    transcriptOutput.value = '';
    durationPill.textContent = '—';
    latencyPill.textContent  = '—';
    state.transcript = '';
  }

  // Recover from any wedged transcribe state (iOS bfcache restore, killed fetch,
  // visibility changes that nuked the in-flight promise, etc.).
  function recoverIfStuck() {
    if (state._transcribeAbort) {
      try { state._transcribeAbort.abort(); } catch (_) {}
      state._transcribeAbort = null;
    }
    if (state.transcribeBusy) {
      setMediaBusy(false);
      hideStreamIndicator();
      streamStatusPill.classList.add('hidden');
      streamingCursor.classList.add('hidden');
    }
  }

  // iOS Safari can restore a page from bfcache with the previous fetch
  // long-dead; without this the buttons stay disabled and the user has to
  // hard-refresh.
  window.addEventListener('pageshow', function (e) {
    if (e.persisted) recoverIfStuck();
  });
  document.addEventListener('visibilitychange', function () {
    // Only recover when the user comes BACK to the tab. Don't kill in-flight
    // requests when they're momentarily backgrounded.
    if (document.visibilityState === 'visible' && state._transcribeAbort === null && state.transcribeBusy) {
      recoverIfStuck();
    }
  });

  transcribeForm.addEventListener('submit', async function (e) {
    e.preventDefault();

    // If something's actually still in flight, do nothing (button should be
    // disabled). If the state lies (bfcache restore left busy=true), recover.
    if (state.transcribeBusy && state._transcribeAbort) return;
    if (state.transcribeBusy) recoverIfStuck();

    var url  = urlInput.value.trim();
    var file = fileInput.files[0] || null;

    if (!url && !file) { showStatus('Paste a URL or choose a file.'); return; }
    if (url && file)   { showStatus('Use a URL or a file — not both.'); return; }

    resetTranscribePanel(false);

    var fd = new FormData();
    if (url)  fd.append('url',  url);
    if (file) fd.append('file', file);

    setMediaBusy(true);
    showStatus(url ? 'Downloading and transcribing…' : 'Uploading and transcribing…');
    showStreamIndicator('Transcribing…');
    resultCard.classList.remove('hidden');
    streamStatusPill.classList.remove('hidden');
    streamingCursor.classList.remove('hidden');

    var controller = new AbortController();
    state._transcribeAbort = controller;
    var finalPayload = {};

    try {
      var res = await fetch('/transcribe/stream', {
        method: 'POST',
        headers: apiHeaders(),
        body: fd,
        signal: controller.signal,
      });

      if (!res.ok) {
        var errJson = await res.json().catch(function () { return {}; });
        throw new Error(errJson.detail || 'Request failed.');
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

          if (evtType === 'chunk') {
            // Join with a space if we already have text and the new chunk
            // doesn't start with one; faster-whisper segments are word-level.
            var existing = transcriptOutput.value;
            var addition = parsed.text || '';
            if (existing && !existing.endsWith(' ') && !addition.startsWith(' ')) {
              transcriptOutput.value = existing + ' ' + addition;
            } else {
              transcriptOutput.value = existing + addition;
            }
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

      state.transcript = transcriptOutput.value.trim();
      transcriptOutput.value = state.transcript;
      durationPill.textContent = 'Duration: ' + Number(finalPayload.duration || 0).toFixed(2) + 's';
      latencyPill.textContent  = 'Latency: '  + Number(finalPayload.latency  || 0).toFixed(2) + 's';
      hideStatus();
      hideStreamIndicator();
      streamStatusPill.classList.add('hidden');
      streamingCursor.classList.add('hidden');

    } catch (err) {
      if (err.name === 'AbortError') {
        // Cancelled by recoverIfStuck or page hide — silent.
      } else {
        hideStatus();
        hideStreamIndicator();
        streamStatusPill.classList.add('hidden');
        streamingCursor.classList.add('hidden');
        showStatus(err.message || 'Transcription failed.');
      }
    } finally {
      state._transcribeAbort = null;
      setMediaBusy(false);
    }
  });

  // ─── Media: downloads ──────────────────────────────────────────────────────

  async function triggerDownload(endpoint, pendingMessage, doneMessage) {
    var url = urlInput.value.trim();
    if (!url) { showStatus('Paste a media URL to download.'); return; }
    if (!state.apiKey) { showStatus('Enter the shared key first.'); return; }

    setMediaBusy(true);
    showStatus(pendingMessage);

    try {
      var body = new URLSearchParams();
      body.set('url', url);

      var res = await fetch(endpoint, {
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

      showStatus(doneMessage);
      setTimeout(hideStatus, 4000);
    } catch (err) {
      showStatus(err.message || 'Download failed.');
    } finally {
      setMediaBusy(false);
    }
  }

  downloadAudioBtn.addEventListener('click', function () {
    triggerDownload('/download-audio', 'Preparing audio download…', 'Audio download complete.');
  });

  downloadBtn.addEventListener('click', function () {
    triggerDownload('/download-video', 'Preparing video download…', 'Video download complete.');
  });

  // ─── Media: copy transcript ────────────────────────────────────────────────

  copyBtn.addEventListener('click', function () {
    var text = transcriptOutput.value;
    if (!text) return;
    var original = copyBtn.textContent;
    copyToClipboard(text).then(function () {
      copyBtn.textContent = 'Copied';
      toast('Transcript copied');
      setTimeout(function () { copyBtn.textContent = original; }, 1600);
    }).catch(function () {
      copyBtn.textContent = 'Copy failed';
      toast('Copy failed — long-press the text to copy manually');
      setTimeout(function () { copyBtn.textContent = original; }, 2000);
    });
  });

  // ─── Media: download transcript as .txt ───────────────────────────────────

  function buildTranscriptFilename() {
    var url = urlInput.value.trim();
    var slug = '';
    if (url) {
      try {
        var u = new URL(url);
        slug = (u.hostname.replace(/^www\./, '') + u.pathname)
          .replace(/[^a-z0-9]+/gi, '-')
          .replace(/^-+|-+$/g, '')
          .slice(0, 60);
      } catch (_) {}
    }
    if (!slug && fileInput.files[0]) {
      slug = fileInput.files[0].name.replace(/\.[^.]+$/, '').slice(0, 60);
    }
    var stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
    return 'transcript-' + (slug || stamp) + '.txt';
  }

  downloadTxtBtn.addEventListener('click', function () {
    var text = transcriptOutput.value;
    if (!text) { toast('Nothing to download yet'); return; }
    var blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    var objUrl = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = objUrl;
    a.download = buildTranscriptFilename();
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(objUrl);
  });

  // ─── Media: "Chat about this" ──────────────────────────────────────────────

  chatCtxBtn.addEventListener('click', async function () {
    if (!state.transcript) return;
    // Fresh thread anchored to the new transcript; clear any prior state.
    resetChatScreen();
    setChatContext(state.transcript, 'transcript');
    state.currentThreadId = null;  // sendChat() will create on first send
    switchPage('chat');
  });

  // ─── Chat: context ─────────────────────────────────────────────────────────

  function setChatContext(text, label) {
    state.chatContext = text;
    state.chatContextLabel = label || 'transcript';
    contextLabel.textContent = 'Context: ' + (state.chatContextLabel.length > 36
      ? state.chatContextLabel.slice(0, 33) + '…'
      : state.chatContextLabel);
    contextBar.classList.remove('hidden');
    if (quickActions) quickActions.classList.remove('hidden');
  }

  function clearChatContext() {
    state.chatContext = null;
    state.chatContextLabel = '';
    contextBar.classList.add('hidden');
    if (quickActions) quickActions.classList.add('hidden');
    // The anchor changed — next send should start a new thread.
    state.currentThreadId = null;
  }

  clearContextBtn.addEventListener('click', clearChatContext);

  // ─── Chat: quick-action chips ──────────────────────────────────────────────

  if (quickActions) {
    quickActions.addEventListener('click', function (e) {
      var chip = e.target.closest('.chip');
      if (!chip || state.chatStreaming) return;
      var prompt = chip.dataset.prompt;
      if (!prompt) return;
      chatInput.value = prompt;
      autoGrow(chatInput);
      sendChat();
    });
  }

  // ─── Chat: message rendering ───────────────────────────────────────────────

  function hideWelcome() {
    var w = document.getElementById('welcome-msg');
    if (w) w.style.display = 'none';
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
    var textNode = document.createTextNode(token);
    state._streamBubble.insertBefore(textNode, state._streamCursor);
    scrollToBottom();
  }

  function finalizeStream(fullText) {
    if (state._streamBubble && state._streamCursor) {
      state._streamCursor.remove();
      state._streamCursor = null;
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

    // Lazily create a thread on first send so empty chats don't pollute history.
    if (!state.currentThreadId) {
      try {
        state.currentThreadId = await ensureCurrentThread(model);
      } catch (err) {
        appendErrorMsg(err.message || 'Could not create chat thread.');
        return;
      }
    }

    appendMessage('user', text);
    state.chatMessages.push({ role: 'user', content: text });
    chatInput.value = '';
    autoGrow(chatInput);

    setChatBusy(true);

    var requestBody = {
      message:    text,
      history:    state.chatMessages.slice(0, -1),
      model:      model,
      thread_id:  state.currentThreadId,
    };
    if (state.chatContext) {
      requestBody.transcript_context = state.chatContext;
    }

    var fullResponse = '';
    beginStreamBubble();

    var controller = new AbortController();
    state._chatAbort = controller;

    try {
      var res = await fetch('/chat/stream', {
        method: 'POST',
        headers: apiHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(requestBody),
        signal: controller.signal,
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
      finalizeStream(fullResponse);
      if (err.name !== 'AbortError') {
        appendErrorMsg(err.message || 'Something went wrong.');
        state.chatMessages.pop();   // roll back the user message
      }
    } finally {
      state._chatAbort = null;
      setChatBusy(false);
      chatInput.focus();
    }
  }

  sendBtn.addEventListener('click', sendChat);

  stopBtn.addEventListener('click', function () {
    if (state._chatAbort) {
      try { state._chatAbort.abort(); } catch (_) {}
    }
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

  function resetChatScreen() {
    state.chatMessages = [];
    messagesEl.innerHTML = '';
    var welcome = document.createElement('div');
    welcome.className = 'welcome-msg';
    welcome.id = 'welcome-msg';
    welcome.innerHTML =
      '<div class="welcome-icon"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg></div>' +
      '<p class="welcome-title">Chat</p>' +
      '<p class="welcome-body">Talk to a local model about your transcripts. Transcribe something on Media, ' +
      'then tap <strong>Chat about this</strong> to load it as context.</p>';
    messagesEl.appendChild(welcome);
  }

  clearChatBtn.addEventListener('click', function () {
    resetChatScreen();
    state.currentThreadId = null;
    toast('New chat');
  });

  // ─── Attach context sheet ─────────────────────────────────────────────────

  function showAttachChoices() {
    attachChoices.classList.remove('hidden');
    attachPaste.classList.add('hidden');
  }
  function showAttachPaste() {
    attachChoices.classList.add('hidden');
    attachPaste.classList.remove('hidden');
    setTimeout(function () { attachText.focus(); }, 50);
  }

  function openAttachSheet() {
    attachText.value = state.chatContext || '';
    attachFile.value = '';
    attachImage.value = '';
    showAttachChoices();
    attachSheet.classList.remove('hidden');
    attachBackdrop.classList.remove('hidden');
    attachSheet.setAttribute('aria-hidden', 'false');
  }

  function closeAttachSheet() {
    attachSheet.classList.add('hidden');
    attachBackdrop.classList.add('hidden');
    attachSheet.setAttribute('aria-hidden', 'true');
  }

  function applyContext(text, label) {
    state.currentThreadId = null;
    resetChatScreen();
    setChatContext(text, label);
    closeAttachSheet();
    switchPage('chat');
    toast('Context attached');
  }

  attachCtxBtn.addEventListener('click', openAttachSheet);
  attachCloseBtn.addEventListener('click', closeAttachSheet);
  attachBackdrop.addEventListener('click', closeAttachSheet);
  attachBackBtn.addEventListener('click', showAttachChoices);
  attachChoicePaste.addEventListener('click', showAttachPaste);

  // Pick a text file → load + apply immediately
  attachFile.addEventListener('change', function () {
    var f = attachFile.files[0];
    if (!f) return;
    var reader = new FileReader();
    reader.onload = function () {
      var text = String(reader.result || '').trim();
      if (!text) { toast('File looked empty'); return; }
      applyContext(text, f.name);
    };
    reader.onerror = function () { toast('Could not read file'); };
    reader.readAsText(f);
  });

  // Pick an image → stash but warn; current chat models can't see images.
  attachImage.addEventListener('change', function () {
    var f = attachImage.files[0];
    if (!f) return;
    toast('Vision needs a multimodal model — coming with LM Studio integration');
    attachImage.value = '';
  });

  attachApplyBtn.addEventListener('click', function () {
    var text = attachText.value.trim();
    if (!text) { toast('Paste something first'); return; }
    applyContext(text, 'pasted text');
  });

  // ─── Threads: persistence, sheet, resume ──────────────────────────────────

  async function ensureCurrentThread(model) {
    var body = { model: model || '' };
    if (state.chatContext) body.transcript_context = state.chatContext;
    var res = await fetch('/chat/threads', {
      method: 'POST',
      headers: apiHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      var err = await res.json().catch(function () { return {}; });
      throw new Error(err.detail || 'Could not create thread.');
    }
    var thread = await res.json();
    return thread.id;
  }

  function formatThreadStamp(ts) {
    if (!ts) return '';
    var d = new Date(ts * 1000);
    var now = new Date();
    var sameDay = d.toDateString() === now.toDateString();
    if (sameDay) {
      return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    }
    var yesterday = new Date(now); yesterday.setDate(now.getDate() - 1);
    if (d.toDateString() === yesterday.toDateString()) return 'Yesterday';
    var diff = (now - d) / 86400000;
    if (diff < 7) return d.toLocaleDateString([], { weekday: 'short' });
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  }

  function renderThreadList(threads) {
    threadList.innerHTML = '';
    if (!threads.length) {
      threadsEmpty.classList.remove('hidden');
      return;
    }
    threadsEmpty.classList.add('hidden');

    threads.forEach(function (t) {
      var li = document.createElement('li');
      li.className = 'thread-item';
      if (t.id === state.currentThreadId) li.classList.add('is-active');

      var main = document.createElement('div');
      main.className = 'thread-item-main';

      var title = document.createElement('div');
      title.className = 'thread-item-title';
      if (t.title && t.title.trim()) {
        title.textContent = t.title;
      } else {
        title.classList.add('is-empty');
        title.textContent = 'Untitled chat';
      }

      var meta = document.createElement('div');
      meta.className = 'thread-item-meta';
      if (t.transcript_hash) {
        var badge = document.createElement('span');
        badge.className = 'thread-item-badge';
        badge.textContent = 'transcript';
        meta.appendChild(badge);
      }
      var stamp = document.createElement('span');
      stamp.textContent = formatThreadStamp(t.updated_at);
      meta.appendChild(stamp);
      var count = document.createElement('span');
      count.textContent = (t.message_count || 0) + ' msg';
      meta.appendChild(count);
      if (t.model) {
        var model = document.createElement('span');
        model.textContent = t.model;
        meta.appendChild(model);
      }

      main.appendChild(title);
      main.appendChild(meta);

      var delBtn = document.createElement('button');
      delBtn.className = 'thread-item-delete';
      delBtn.setAttribute('aria-label', 'Delete chat');
      delBtn.innerHTML =
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<polyline points="3 6 5 6 21 6"/><path d="M19 6l-2 14a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L5 6"/>' +
        '<path d="M10 11v6M14 11v6M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>';
      delBtn.addEventListener('click', async function (e) {
        e.stopPropagation();
        try {
          var res = await fetch('/chat/threads/' + encodeURIComponent(t.id), {
            method: 'DELETE',
            headers: apiHeaders(),
          });
          if (!res.ok) throw new Error('delete failed');
          if (t.id === state.currentThreadId) {
            state.currentThreadId = null;
            resetChatScreen();
          }
          await refreshThreadList();
        } catch (_) {
          // Silent: row will reappear on next refresh.
        }
      });

      li.appendChild(main);
      li.appendChild(delBtn);
      li.addEventListener('click', function () { resumeThread(t); });
      threadList.appendChild(li);
    });
  }

  async function refreshThreadList() {
    var url = '/chat/threads';
    if (state.chatContext) {
      url += '?transcript_context=' + encodeURIComponent(state.chatContext);
    }
    try {
      var res = await fetch(url, { headers: apiHeaders() });
      if (!res.ok) throw new Error('list failed');
      var data = await res.json();
      renderThreadList(data.threads || []);
      threadsSheetTitle.textContent = state.chatContext
        ? 'Chats for this transcript'
        : 'All chats';
    } catch (err) {
      threadList.innerHTML = '';
      threadsEmpty.classList.remove('hidden');
      threadsEmpty.textContent = 'Could not load chats.';
    }
  }

  async function resumeThread(thread) {
    closeThreadsSheet();
    try {
      var res = await fetch('/chat/threads/' + encodeURIComponent(thread.id) + '/messages', {
        headers: apiHeaders(),
      });
      if (!res.ok) throw new Error('load failed');
      var data = await res.json();
      var msgs = data.messages || [];

      state.currentThreadId = thread.id;
      state.chatMessages = msgs.map(function (m) {
        return { role: m.role, content: m.content };
      });

      if (data.thread && data.thread.transcript_text) {
        setChatContext(data.thread.transcript_text, 'transcript');
      } else {
        clearChatContext();
        state.currentThreadId = thread.id;
      }

      messagesEl.innerHTML = '';
      if (!msgs.length) {
        resetChatScreen();
      } else {
        state.chatMessages.forEach(function (m) {
          appendMessage(m.role, m.content);
        });
      }

      if (data.thread && data.thread.model) {
        var stored = data.thread.model;
        var opts = chatModelSelect.options;
        // Exact match first; then match by trailing model name for legacy rows
        // saved before the provider prefix existed.
        var match = Array.prototype.find.call(opts, function (o) { return o.value === stored; });
        if (!match && stored.indexOf(':') === -1) {
          match = Array.prototype.find.call(opts, function (o) {
            return o.value.endsWith(':' + stored);
          });
        }
        if (match) chatModelSelect.value = match.value;
      }
    } catch (err) {
      appendErrorMsg('Could not load that chat.');
    }
  }

  function openThreadsSheet() {
    threadsSheet.classList.remove('hidden');
    threadsBackdrop.classList.remove('hidden');
    threadsSheet.setAttribute('aria-hidden', 'false');
    refreshThreadList();
  }

  function closeThreadsSheet() {
    threadsSheet.classList.add('hidden');
    threadsBackdrop.classList.add('hidden');
    threadsSheet.setAttribute('aria-hidden', 'true');
  }

  threadsBtn.addEventListener('click', openThreadsSheet);
  threadsCloseBtn.addEventListener('click', closeThreadsSheet);
  threadsBackdrop.addEventListener('click', closeThreadsSheet);

  // ─── Models: memory + load/unload ─────────────────────────────────────────

  function formatBytes(n) {
    if (!n || n < 0) return '0 B';
    if (n < 1024) return n + ' B';
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
    if (n < 1024 * 1024 * 1024) return (n / (1024 * 1024)).toFixed(0) + ' MB';
    return (n / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
  }

  function el(tag, attrs, children) {
    var n = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === 'class') n.className = attrs[k];
        else if (k === 'text') n.textContent = attrs[k];
        else if (k === 'html') n.innerHTML = attrs[k];
        else n.setAttribute(k, attrs[k]);
      });
    }
    if (children) {
      (Array.isArray(children) ? children : [children]).forEach(function (c) {
        if (c == null) return;
        n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
      });
    }
    return n;
  }

  function renderModelRow(backend, model, availableBytes) {
    var nameLine = el('div', { class: 'model-row-name', text: model.name });
    var sizeStr = model.size_bytes ? formatBytes(model.size_bytes) : '?';
    var metaParts = [el('span', { text: sizeStr })];
    if (model.loaded) {
      metaParts.push(el('span', { class: 'model-badge loaded', text: 'loaded' }));
    } else if (model.ram_estimate_bytes && availableBytes && model.ram_estimate_bytes > availableBytes) {
      metaParts.push(el('span', { class: 'model-badge warn', text: 'may swap' }));
    }
    var meta = el('div', { class: 'model-row-meta' }, metaParts);
    var main = el('div', { class: 'model-row-main' }, [nameLine, meta]);

    var btn = el('button', {
      class: 'model-action-btn ' + (model.loaded ? 'is-unload' : 'is-load'),
      text: model.loaded ? 'Unload' : 'Load',
    });
    btn.addEventListener('click', function () {
      handleModelAction(backend, model, model.loaded ? 'unload' : 'load', availableBytes, btn);
    });
    var actions = el('div', { class: 'model-row-actions' }, [btn]);
    return el('div', { class: 'model-row' }, [main, actions]);
  }

  async function handleModelAction(backend, model, action, availableBytes, btn) {
    if (action === 'load' && model.ram_estimate_bytes && availableBytes &&
        model.ram_estimate_bytes > availableBytes) {
      var ok = window.confirm(
        'Loading ' + model.name + ' needs roughly ' + formatBytes(model.ram_estimate_bytes) +
        '; only ' + formatBytes(availableBytes) + ' is free. This may push you into swap. Continue?'
      );
      if (!ok) return;
    }

    btn.disabled = true;
    var origText = btn.textContent;
    btn.textContent = action === 'load' ? 'Loading…' : 'Unloading…';
    try {
      var res = await fetch('/system/' + action, {
        method: 'POST',
        headers: apiHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ backend: backend, name: model.name }),
      });
      if (!res.ok) {
        var err = await res.json().catch(function () { return {}; });
        throw new Error(err.detail || (action + ' failed'));
      }
      await refreshModelsSheet();
      loadChatModels();
    } catch (err) {
      btn.disabled = false;
      btn.textContent = origText;
      window.alert('Error: ' + (err.message || 'unknown'));
    }
  }

  function renderBackendSection(label, backendKey, inventory, availableBytes) {
    var title = el('div', { class: 'models-section-title', text: label });
    var section = el('div', { class: 'models-section' }, [title]);
    var installed = (inventory && inventory.installed) || [];
    if (!installed.length) {
      var emptyText = inventory && inventory.reachable === false
        ? backendKey + ' is not reachable.'
        : 'No models installed.';
      section.appendChild(el('div', { class: 'backend-empty', text: emptyText }));
      return section;
    }
    installed.sort(function (a, b) {
      if (a.loaded !== b.loaded) return a.loaded ? -1 : 1;
      return (b.size_bytes || 0) - (a.size_bytes || 0);
    });
    installed.forEach(function (m) {
      section.appendChild(renderModelRow(backendKey, m, availableBytes));
    });
    return section;
  }

  function renderModelsSheet(data) {
    modelsBody.innerHTML = '';
    if (!data) {
      modelsBody.appendChild(el('div', { class: 'loading-line', text: 'Could not load status.' }));
      return;
    }

    var mem = data.memory || {};
    var availableBytes = mem.available_bytes || 0;
    var pressure = mem.pressure || 'low';

    var sysTitle = el('div', { class: 'models-section-title', text: 'System' });
    var pct = (mem.used_bytes && mem.total_bytes) ? (mem.used_bytes / mem.total_bytes * 100) : 0;
    var bar = el('div', { class: 'mem-bar' }, [
      el('div', { class: 'mem-bar-fill pressure-' + pressure, style: 'width:' + pct.toFixed(1) + '%' }),
    ]);
    var swapStr = mem.swap_used_bytes
      ? ' · Swap ' + formatBytes(mem.swap_used_bytes)
      : '';
    var metaLine = el('div', { class: 'mem-meta' }, [
      el('span', { html:
        '<strong>' + formatBytes(mem.used_bytes || 0) + '</strong> / ' +
        formatBytes(mem.total_bytes || 0) + ' used'
      }),
      el('span', { html: '<strong>' + formatBytes(availableBytes) + '</strong> free' + swapStr }),
      el('span', { html: '<span class="pressure-dot ' + pressure + '"></span>' + pressure + ' pressure' }),
    ]);
    var sysSection = el('div', { class: 'models-section' }, [sysTitle, bar, metaLine]);
    modelsBody.appendChild(sysSection);

    var w = data.whisper || {};
    if (w.name) {
      var wTitle = el('div', { class: 'models-section-title', text: 'Transcription' });
      var wRow = el('div', { class: 'model-row' }, [
        el('div', { class: 'model-row-main' }, [
          el('div', { class: 'model-row-name', text: 'Whisper ' + w.name }),
          el('div', { class: 'model-row-meta' }, [
            el('span', { text: (w.backend || '') + (w.device ? ' · ' + w.device : '') }),
            w.loaded ? el('span', { class: 'model-badge loaded', text: 'loaded' }) : null,
          ].filter(Boolean)),
        ]),
      ]);
      modelsBody.appendChild(el('div', { class: 'models-section' }, [wTitle, wRow]));
    }

    modelsBody.appendChild(renderBackendSection('Ollama', 'ollama', data.ollama, availableBytes));
    modelsBody.appendChild(renderBackendSection('LM Studio', 'lmstudio', data.lmstudio, availableBytes));
  }

  async function refreshModelsSheet() {
    modelsBody.innerHTML = '';
    modelsBody.appendChild(el('div', { class: 'loading-line', text: 'Loading…' }));
    try {
      var res = await fetch('/system/status', { headers: apiHeaders() });
      if (!res.ok) throw new Error();
      var data = await res.json();
      renderModelsSheet(data);
    } catch (_) {
      renderModelsSheet(null);
    }
  }

  function openModelsSheet() {
    modelsSheet.classList.remove('hidden');
    modelsBackdrop.classList.remove('hidden');
    modelsSheet.setAttribute('aria-hidden', 'false');
    refreshModelsSheet();
  }

  function closeModelsSheet() {
    modelsSheet.classList.add('hidden');
    modelsBackdrop.classList.add('hidden');
    modelsSheet.setAttribute('aria-hidden', 'true');
  }

  modelsBtn.addEventListener('click', openModelsSheet);
  modelsCloseBtn.addEventListener('click', closeModelsSheet);
  modelsBackdrop.addEventListener('click', closeModelsSheet);
  modelsRefreshBtn.addEventListener('click', refreshModelsSheet);

  // ─── Boot ─────────────────────────────────────────────────────────────────

  function init() {
    var stored = localStorage.getItem(STORAGE_KEY) || '';
    apiKeyInput.value = stored;
    persistKey(stored);
    keyToggleBtn.classList.toggle('active', !!stored);

    loadServiceHealth();
    loadChatModels();
  }

  init();

})();

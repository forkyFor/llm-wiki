/* LLM Wiki — frontend application */
'use strict';

const API = '';  // same origin

// ── State ────────────────────────────────────────────────────────────────────
let treeData      = [];       // file/folder tree from API
let messages      = [];
let streaming     = false;
let expandedFolders = new Set(); // paths of expanded folders
let selectedFolder  = '';        // upload target folder path ('' = root)
let creatingFolder  = null;      // null | string — parent path for new folder input
let pendingDelete   = null;      // null | {type:'file'|'folder', path, name}

// ── DOM refs ─────────────────────────────────────────────────────────────────
const fileList          = document.getElementById('file-list');
const fileEmpty         = document.getElementById('file-empty');
const fileCount         = document.getElementById('file-count');
const dropZone          = document.getElementById('drop-zone');
const fileInput         = document.getElementById('file-input');
const messagesEl        = document.getElementById('messages');
const chatEmpty         = document.getElementById('chat-empty');
const chatInput         = document.getElementById('chat-input');
const sendBtn           = document.getElementById('send-btn');
const ollamaDot         = document.getElementById('ollama-dot');
const ollamaLabel       = document.getElementById('ollama-label');
const modal             = document.getElementById('modal');
const modalTitle        = document.getElementById('modal-title');
const modalText         = document.getElementById('modal-text');
const modalConfirm      = document.getElementById('modal-confirm');
const modalCancel       = document.getElementById('modal-cancel');
const newRootFolderBtn  = document.getElementById('new-root-folder-btn');
const uploadTarget      = document.getElementById('upload-target');
const uploadTargetPath  = document.getElementById('upload-target-path');
const uploadTargetClear = document.getElementById('upload-target-clear');

// ── Helpers ──────────────────────────────────────────────────────────────────
function fmtSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1048576).toFixed(1) + ' MB';
}

function fileIcon(name) {
  const ext = name.split('.').pop().toLowerCase();
  const map = { pdf: '📄', png: '🖼️', jpg: '🖼️', jpeg: '🖼️',
                bmp: '🖼️', tiff: '🖼️', webp: '🖼️', txt: '📝', md: '📝', docx: '📝', doc: '📝' };
  return map[ext] || '📁';
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function countFiles(items) {
  let n = 0;
  for (const item of items) {
    if (item.type === 'file') n++;
    else n += countFiles(item.children || []);
  }
  return n;
}

// ── Ollama status check ──────────────────────────────────────────────────────
async function checkOllama() {
  try {
    const r = await fetch('/api/files');
    if (r.ok) {
      ollamaDot.className = 'status-dot ok';
      ollamaLabel.textContent = 'Online';
    } else throw new Error();
  } catch {
    ollamaDot.className = 'status-dot err';
    ollamaLabel.textContent = 'Backend non raggiungibile';
  }
}

// ── File tree loading ─────────────────────────────────────────────────────────
async function loadFiles() {
  if (creatingFolder !== null) return; // don't reset tree while user is typing a folder name
  try {
    const r = await fetch(`${API}/api/files`);
    if (!r.ok) return;
    treeData = await r.json();
  } catch { return; }
  renderFiles();
}

// ── Tree rendering ────────────────────────────────────────────────────────────
function renderCreateInput(depth) {
  const pl = 8 + depth * 16;
  return `<div class="folder-create-row" style="padding-left:${pl}px">
    <span style="font-size:15px;flex-shrink:0">📁</span>
    <input class="folder-name-input" id="folder-name-input"
           placeholder="Nome cartella" maxlength="60" autocomplete="off" />
    <button class="item-btn confirm-btn" id="folder-create-confirm" title="Crea (Invio)">✓</button>
    <button class="item-btn cancel-btn"  id="folder-create-cancel"  title="Annulla (Esc)">✕</button>
  </div>`;
}

function renderTreeItems(items, depth) {
  let html = '';
  for (const item of items) {
    const pl = 8 + depth * 16;
    if (item.type === 'folder') {
      const isOpen   = expandedFolders.has(item.path);
      const isSel    = selectedFolder === item.path;
      html += `<div class="tree-folder${isSel ? ' selected' : ''}"
                    data-path="${escHtml(item.path)}"
                    style="padding-left:${pl}px">
        <span class="chevron${isOpen ? ' open' : ''}">▶</span>
        <span class="folder-icon">📁</span>
        <span class="item-name" title="${escHtml(item.name)}">${escHtml(item.name)}</span>
        <button class="item-btn new-subfolder-btn" data-path="${escHtml(item.path)}"
                title="Nuova sottocartella">+</button>
        <button class="item-btn folder-del-btn" data-path="${escHtml(item.path)}"
                data-name="${escHtml(item.name)}" title="Elimina cartella">🗑</button>
      </div>`;
      if (isOpen) {
        html += renderTreeItems(item.children || [], depth + 1);
        if (creatingFolder === item.path) {
          html += renderCreateInput(depth + 1);
        }
      }
    } else {
      html += `<div class="file-item" data-path="${escHtml(item.path)}"
                    style="padding-left:${pl + 16}px">
        <span class="file-icon">${fileIcon(item.name)}</span>
        <div class="file-info">
          <div class="file-name" title="${escHtml(item.name)}">${escHtml(item.name)}</div>
          <div class="file-size">${fmtSize(item.size)}</div>
        </div>
        <span class="file-status status-${item.status}">${item.status}</span>
        <button class="delete-btn item-btn file-del-btn"
                data-path="${escHtml(item.path)}" data-name="${escHtml(item.name)}"
                title="Elimina">🗑</button>
      </div>`;
    }
  }
  return html;
}

function updateUploadTargetUI() {
  if (selectedFolder) {
    uploadTarget.style.display = 'flex';
    uploadTargetPath.textContent = '→ ' + selectedFolder;
  } else {
    uploadTarget.style.display = 'none';
  }
}

function renderFiles() {
  const isEmpty = treeData.length === 0 && creatingFolder === null;
  if (isEmpty) {
    fileList.innerHTML = '';
    fileList.appendChild(fileEmpty);
    fileEmpty.style.display = '';
    fileCount.textContent = '0 file';
    updateUploadTargetUI();
    return;
  }

  fileEmpty.style.display = 'none';
  let html = renderTreeItems(treeData, 0);
  if (creatingFolder === '') {
    html += renderCreateInput(0);
  }
  fileList.innerHTML = html;
  fileCount.textContent = countFiles(treeData) + ' file';
  updateUploadTargetUI();

  // Wire up folder creation input if visible
  if (creatingFolder !== null) {
    const inp = document.getElementById('folder-name-input');
    const confirmBtn = document.getElementById('folder-create-confirm');
    const cancelBtn  = document.getElementById('folder-create-cancel');
    if (inp) {
      inp.focus();
      inp.addEventListener('keydown', handleFolderInputKey);
    }
    // mousedown+preventDefault prevents input blur before click fires
    if (confirmBtn) confirmBtn.addEventListener('mousedown', e => { e.preventDefault(); confirmCreateFolder(); });
    if (cancelBtn)  cancelBtn.addEventListener('mousedown', e => { e.preventDefault(); cancelCreateFolder(); });
  }
}

// ── Tree interactions (event delegation) ─────────────────────────────────────
fileList.addEventListener('click', e => {
  // New subfolder
  const newBtn = e.target.closest('.new-subfolder-btn');
  if (newBtn) {
    e.stopPropagation();
    const path = newBtn.dataset.path;
    expandedFolders.add(path); // auto-expand parent
    creatingFolder = path;
    renderFiles();
    return;
  }

  // Delete folder
  const folderDelBtn = e.target.closest('.folder-del-btn');
  if (folderDelBtn) {
    e.stopPropagation();
    openDeleteFolderModal(folderDelBtn.dataset.path, folderDelBtn.dataset.name);
    return;
  }

  // Delete file
  const fileDelBtn = e.target.closest('.file-del-btn');
  if (fileDelBtn) {
    e.stopPropagation();
    openDeleteFileModal(fileDelBtn.dataset.path, fileDelBtn.dataset.name);
    return;
  }

  // Folder row click → toggle expand + set upload target
  const folderRow = e.target.closest('.tree-folder');
  if (folderRow) {
    const path = folderRow.dataset.path;
    if (expandedFolders.has(path)) expandedFolders.delete(path);
    else expandedFolders.add(path);
    selectedFolder = selectedFolder === path ? '' : path;
    if (creatingFolder !== null && creatingFolder !== path) {
      creatingFolder = null;
    }
    renderFiles();
    return;
  }

  // File row click → open file
  const fileRow = e.target.closest('.file-item');
  if (fileRow && !e.target.closest('.item-btn')) {
    const path = fileRow.dataset.path;
    window.open(`${API}/api/files/${path}`, '_blank');
  }
});

// ── New root folder ───────────────────────────────────────────────────────────
newRootFolderBtn.addEventListener('click', () => {
  creatingFolder = '';
  renderFiles();
});

uploadTargetClear.addEventListener('click', () => {
  selectedFolder = '';
  updateUploadTargetUI();
});

// ── Folder creation ───────────────────────────────────────────────────────────
function handleFolderInputKey(e) {
  if (e.key === 'Enter') { e.preventDefault(); confirmCreateFolder(); }
  if (e.key === 'Escape') { e.preventDefault(); cancelCreateFolder(); }
}

function cancelCreateFolder() {
  creatingFolder = null;
  renderFiles();
}

async function confirmCreateFolder() {
  const inp = document.getElementById('folder-name-input');
  if (!inp) return;
  const name = inp.value.trim();
  if (!name) { cancelCreateFolder(); return; }
  const parentPath = creatingFolder; // capture before reset
  const path = parentPath ? `${parentPath}/${name}` : name;

  try {
    const r = await fetch(`${API}/api/folders`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      alert('Errore: ' + (err.detail || r.statusText));
      return;
    }
    if (parentPath !== null) expandedFolders.add(parentPath || path);
    creatingFolder = null;
    await loadFiles();
  } catch (e) {
    alert('Errore: ' + e.message);
  }
}

// ── Upload ───────────────────────────────────────────────────────────────────
async function uploadFile(file) {
  const fd = new FormData();
  fd.append('file', file);
  const url = selectedFolder
    ? `${API}/api/files?folder=${encodeURIComponent(selectedFolder)}`
    : `${API}/api/files`;
  try {
    const r = await fetch(url, { method: 'POST', body: fd });
    if (!r.ok) { alert('Upload fallito: ' + r.statusText); return; }
    // Auto-expand target folder so user sees uploaded file
    if (selectedFolder) expandedFolders.add(selectedFolder);
    await loadFiles();
  } catch (e) {
    alert('Upload error: ' + e.message);
  }
}

dropZone.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', async e => {
  for (const f of e.target.files) await uploadFile(f);
  fileInput.value = '';
});

dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', async e => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  for (const f of e.dataTransfer.files) await uploadFile(f);
});

// ── Delete modals ─────────────────────────────────────────────────────────────
function openDeleteFileModal(path, name) {
  pendingDelete = { type: 'file', path };
  modalTitle.textContent = 'Elimina file';
  modalText.textContent = `Eliminare "${name}" e tutte le pagine wiki associate? Operazione irreversibile.`;
  modal.classList.add('visible');
}

function openDeleteFolderModal(path, name) {
  pendingDelete = { type: 'folder', path };
  modalTitle.textContent = 'Elimina cartella';
  modalText.textContent = `Eliminare la cartella "${name}" e tutto il suo contenuto? Verranno rimosse anche le pagine wiki associate. Operazione irreversibile.`;
  modal.classList.add('visible');
}

modalCancel.addEventListener('click', () => {
  modal.classList.remove('visible');
  pendingDelete = null;
});

modalConfirm.addEventListener('click', async () => {
  if (!pendingDelete) return;
  modal.classList.remove('visible');
  const { type, path } = pendingDelete;
  pendingDelete = null;
  try {
    const url = type === 'folder' ? `${API}/api/folders/${path}` : `${API}/api/files/${path}`;
    const r = await fetch(url, { method: 'DELETE' });
    if (!r.ok) { alert('Eliminazione fallita: ' + r.statusText); }
  } catch (e) { alert('Errore: ' + e.message); }
  // Clean up any selection pointing to deleted path
  if (type === 'folder') {
    expandedFolders.delete(path);
    if (selectedFolder === path || selectedFolder.startsWith(path + '/')) selectedFolder = '';
  }
  await loadFiles();
});

// ── Chat ─────────────────────────────────────────────────────────────────────
function renderMessages() {
  if (messages.length === 0) {
    messagesEl.innerHTML = '';
    messagesEl.appendChild(chatEmpty);
    return;
  }
  chatEmpty.style.display = 'none';

  const html = messages.map((m, i) => {
    if (m.role === 'user') {
      return `<div class="msg user"><div class="msg-bubble">${escHtml(m.content)}</div></div>`;
    }
    const sourcesHtml = (m.sources && m.sources.length > 0)
      ? `<div class="sources">${m.sources.map(s =>
          `<a class="source-chip" href="${API}/api/files/${encodeURIComponent(s)}" target="_blank" title="${escHtml(s)}">${escHtml(s)}</a>`
        ).join('')}</div>`
      : '';
    return `<div class="msg assistant" data-idx="${i}">
      <div class="msg-bubble">${escHtml(m.content)}</div>
      ${sourcesHtml}
    </div>`;
  }).join('');

  messagesEl.innerHTML = html;
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function addStreamToken(token) {
  const last = messages[messages.length - 1];
  if (last && last.role === 'assistant' && last.streaming) {
    last.content += token;
    const bubbles = messagesEl.querySelectorAll('.msg.assistant .msg-bubble');
    if (bubbles.length > 0) {
      bubbles[bubbles.length - 1].textContent = last.content;
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
  }
}

async function sendMessage() {
  const text = chatInput.value.trim();
  if (!text || streaming) return;
  streaming = true;
  sendBtn.disabled = true;
  chatInput.value = '';
  chatInput.style.height = 'auto';

  chatEmpty.style.display = 'none';

  messages.push({ role: 'user', content: text });
  messages.push({ role: 'assistant', content: '', sources: [], streaming: true });
  renderMessages();

  const history = messages.slice(0, -1).map(m => ({ role: m.role, content: m.content }));

  try {
    const r = await fetch(`${API}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history }),
    });

    if (!r.ok) {
      messages[messages.length - 1].content = 'Errore: ' + r.statusText;
      messages[messages.length - 1].streaming = false;
      renderMessages();
      return;
    }

    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const parts = buf.split('\n\n');
      buf = parts.pop();
      for (const part of parts) {
        if (!part.startsWith('data: ')) continue;
        try {
          const evt = JSON.parse(part.slice(6));
          if (evt.token) addStreamToken(evt.token);
          if (evt.done) {
            const last = messages[messages.length - 1];
            last.sources = evt.sources || [];
            last.streaming = false;
            renderMessages();
          }
          if (evt.error) {
            const last = messages[messages.length - 1];
            last.content = (last.content || '') + '\n[Errore: ' + evt.error + ']';
            last.streaming = false;
            renderMessages();
          }
        } catch { /* ignore parse errors */ }
      }
    }
  } catch (e) {
    const last = messages[messages.length - 1];
    last.content = 'Errore di connessione: ' + e.message;
    last.streaming = false;
    renderMessages();
  } finally {
    streaming = false;
    sendBtn.disabled = false;
  }
}

sendBtn.addEventListener('click', sendMessage);
chatInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});
chatInput.addEventListener('input', () => {
  chatInput.style.height = 'auto';
  chatInput.style.height = Math.min(chatInput.scrollHeight, 160) + 'px';
});

// ── Auth guard + startup ──────────────────────────────────────────────────────
(async () => {
  const r = await fetch('/api/auth/me');
  if (!r.ok) { window.location.replace('/login.html'); return; }
  const user = await r.json();

  const authUser = document.getElementById('auth-user');
  if (authUser) authUser.textContent = user.username;

  const adminLink = document.getElementById('admin-link');
  if (adminLink && user.is_admin) adminLink.style.display = '';

  const logoutBtn = document.getElementById('logout-btn');
  if (logoutBtn) {
    logoutBtn.style.display = '';
    logoutBtn.addEventListener('click', async () => {
      await fetch('/api/auth/logout', { method: 'POST' });
      window.location.replace('/login.html');
    });
  }

  checkOllama();
  loadFiles();
  setInterval(loadFiles, 5000);
  setInterval(checkOllama, 30000);
})();

// ── Log Panel ─────────────────────────────────────────────────────────────────
(function () {
  const LOG_MAX   = 200;
  const logPanel  = document.getElementById('log-panel');
  const logToggle = document.getElementById('log-toggle');
  const logLines  = document.getElementById('log-lines');
  const logBadge  = document.getElementById('log-badge');

  let errorCount = 0;
  let panelOpen  = false;

  logToggle.addEventListener('click', () => {
    panelOpen = !panelOpen;
    logPanel.classList.toggle('collapsed', !panelOpen);
    if (panelOpen) {
      errorCount = 0;
      logBadge.style.display = 'none';
      logLines.scrollTop = logLines.scrollHeight;
    }
  });

  function appendLine(rec) {
    const line = document.createElement('div');
    line.className = 'log-line log-' + rec.level;

    const ts   = document.createElement('span'); ts.className = 'log-ts';   ts.textContent = rec.ts;
    const name = document.createElement('span'); name.className = 'log-name'; name.textContent = rec.name;
    const msg  = document.createElement('span'); msg.className = 'log-msg';  msg.textContent = rec.msg;

    line.appendChild(ts);
    line.appendChild(name);
    line.appendChild(msg);
    logLines.appendChild(line);

    while (logLines.childElementCount > LOG_MAX) {
      logLines.removeChild(logLines.firstElementChild);
    }

    const nearBottom = logLines.scrollHeight - logLines.scrollTop - logLines.clientHeight < 60;
    if (nearBottom) logLines.scrollTop = logLines.scrollHeight;

    if (!panelOpen && rec.level === 'ERROR') {
      errorCount++;
      logBadge.textContent = errorCount > 99 ? '99+' : String(errorCount);
      logBadge.style.display = 'inline-block';
    }
  }

  function connect() {
    const es = new EventSource('/api/logs/stream');
    es.onmessage = evt => {
      try { appendLine(JSON.parse(evt.data)); } catch { }
    };
    es.onerror = () => {
      appendLine({ ts: '--:--:--', level: 'WARNING', name: 'log-stream', msg: 'Connessione persa, riconnessione…' });
    };
  }

  connect();
})();

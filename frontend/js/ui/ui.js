// ui.js
// Orquestração: dono do estado, dos eventos e do fluxo. Delega transporte
// para API, parsing para MarkdownRenderer e DOM para Renderer.

// ============================================================
// 0. ESTADO (agora explicitamente aqui, não mais em api.js)
// ============================================================
let messagesStore    = [];
let currentThreadId  = crypto.randomUUID();
let isStreaming      = false;
let renderedCount    = 0;
let currentAbort     = null;   // AbortController do stream em andamento

const inputEl = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const chatEl  = document.getElementById('chat-messages');

// ============================================================
// 1. TOAST
// ============================================================
function showToast(msg, type = 'err') {
    const wrap = document.getElementById('toast');
    if (!wrap) return;

    const el = document.createElement('div');
    el.className = 'toast' + (type === 'ok' ? ' ok' : '');

    const ic = document.createElement('i');
    ic.className = type === 'ok'
        ? 'fa-solid fa-circle-check'
        : 'fa-solid fa-triangle-exclamation';

    const span = document.createElement('span');
    span.textContent = msg;

    el.append(ic, span);
    wrap.appendChild(el);

    setTimeout(() => {
        el.style.opacity = '0';
        el.style.transform = 'translateX(20px)';
        setTimeout(() => el.remove(), 300);
    }, 3800);
}

// ============================================================
// 2. COMPOSER / STREAMING STATE
// ============================================================
function setStreamingState(v) {
    isStreaming = v;
    if (!sendBtn || !inputEl) return;

    sendBtn.disabled = v || inputEl.value.trim() === '';
    sendBtn.innerHTML = v
        ? '<i class="fa-solid fa-spinner fa-spin text-xs"></i>'
        : '<i class="fa-solid fa-arrow-up text-xs"></i>';
}

function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 150) + 'px';
}

function usePrompt(p) {
    inputEl.value = p;
    autoResize(inputEl);
    inputEl.focus();
    sendBtn.disabled = false;
}

// ============================================================
// 3. CONEXÃO (orquestra DOM a partir de API.fetchInfo)
// ============================================================
async function checkConnection() {
    const dotEl    = document.getElementById('connection-dot');
    const textEl   = document.getElementById('connection-text');
    const selectEl = document.getElementById('provider-select');

    if (dotEl)  dotEl.className = 'status-dot wait';
    if (textEl) textEl.textContent = 'Conectando...';

    const result = await API.fetchInfo();

    if (result.ok) {
        if (dotEl)  dotEl.className = 'status-dot ok';
        if (textEl) textEl.textContent = 'Conectado';

        if (selectEl) {
            selectEl.innerHTML = '';
            if (result.providers.length > 0) {
                result.providers.forEach(p => {
                    const opt = document.createElement('option');
                    opt.value = p;
                    opt.textContent = p;
                    selectEl.appendChild(opt);
                });
            } else {
                selectEl.innerHTML = '<option value="">Padrão do sistema</option>';
            }
        }
        return;
    }

    if (dotEl)  dotEl.className = 'status-dot err';
    if (textEl) textEl.textContent = 'Desconectado';
    showToast('Não foi possível conectar ao servidor (' + result.baseUrl + ')');
    console.error(result.error);
}

// ============================================================
// 4. CLIPBOARD
// ============================================================
function fallbackCopy(text) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch (e) { /* noop */ }
    ta.remove();
}

function copyMsg(id, btn) {
    const m = messagesStore.find(x => x.id === id);
    if (!m) return;

    const text = typeof m.content === 'string'
        ? m.content
        : JSON.stringify(m.content, null, 2);

    const done = () => {
        btn.innerHTML = '<i class="fa-solid fa-check"></i>Copiado';
        showToast('Copiado para a área de transferência', 'ok');
        setTimeout(() => {
            btn.innerHTML = '<i class="fa-regular fa-copy"></i>Copiar';
        }, 1600);
    };

    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text)
            .then(done)
            .catch(() => { fallbackCopy(text); done(); });
    } else {
        fallbackCopy(text);
        done();
    }
}

// ============================================================
// 5. SESSÃO
// ============================================================
function resetSession() {
    if (currentAbort) currentAbort.abort();   // mata stream órfão
    currentThreadId = crypto.randomUUID();
    messagesStore   = [];
    renderedCount   = 0;
    renderMessages();
    showToast('Nova conversa iniciada', 'ok');
}

// ============================================================
// 6. RENDER DO FEED
// ============================================================
function renderMessages() {
    if (messagesStore.length === 0) {
        renderedCount = 0;
        chatEl.innerHTML = '';
        chatEl.appendChild(Renderer.createEmptyStateElement(usePrompt));
        return;
    }

    if (renderedCount === 0) {
        chatEl.innerHTML = '';
    }

    const fragment = document.createDocumentFragment();
    for (let i = renderedCount; i < messagesStore.length; i++) {
        fragment.appendChild(Renderer.createMessageElement(messagesStore[i], copyMsg));
    }

    if (fragment.childNodes.length > 0) {
        chatEl.appendChild(fragment);
    }

    renderedCount = messagesStore.length;
    chatEl.scrollTop = chatEl.scrollHeight;
}

// ============================================================
// 7. ATUALIZAÇÃO DA ÚLTIMA MENSAGEM
// ============================================================
function scrollIfNearBottom() {
    const isNearBottom = chatEl.scrollHeight - chatEl.scrollTop - chatEl.clientHeight < 120;
    if (isNearBottom) chatEl.scrollTop = chatEl.scrollHeight;
}

function updateLastMessageFast(content) {
    if (messagesStore.length === 0) return;

    const lastMsg = messagesStore[messagesStore.length - 1];
    lastMsg.content = content;

    const bubble = document.getElementById(`bubble-${lastMsg.id}`);
    if (bubble) {
        Renderer.applyRichRendering(bubble, content, false);
    } else {
        renderMessages();
    }

    scrollIfNearBottom();
}

function updateLastMessage(content, isFinished = true) {
    if (messagesStore.length === 0) return;

    const lastMsg = messagesStore[messagesStore.length - 1];
    lastMsg.content = content;

    const bubble = document.getElementById(`bubble-${lastMsg.id}`);
    if (!bubble) {
        renderMessages();
    } else {
        Renderer.applyRichRendering(bubble, content, isFinished);
    }

    scrollIfNearBottom();
}

// ============================================================
// 8. ENVIO + CONSUMO DO STREAM
// ============================================================
async function sendUserMessage(text) {
    if (isStreaming) return;
    if (!text.trim()) return;

    setStreamingState(true);
    messagesStore.push({ id: crypto.randomUUID(), type: 'human', content: text });
    renderMessages();

    const providerEl = document.getElementById('provider-select');
    const provider   = providerEl ? providerEl.value : '';

    const aiMsg = { id: crypto.randomUUID(), type: 'ai', content: '' };
    messagesStore.push(aiMsg);
    renderMessages();

    currentAbort = new AbortController();

    try {
        const stream = API.streamRun({
            threadId: currentThreadId,
            provider,
            messages: messagesStore,
            signal: currentAbort.signal,
        });

        for await (const event of stream) {
            handleStreamEvent(event, aiMsg);
        }

        updateLastMessage(aiMsg.content, true);

    } catch (err) {
        if (err.name === 'AbortError') return;   // reset intencional, silencioso

        showToast('Erro ao enviar mensagem: ' + err.message);
        const last = messagesStore[messagesStore.length - 1];
        if (last && last.type === 'ai' && !last.content) {
            messagesStore.pop();
            renderMessages();
        }
    } finally {
        currentAbort = null;
        setStreamingState(false);
    }
}

/**
 * Interpreta um evento SSE já parseado pelo API e aplica no estado/UI.
 * Aqui mora a regra de negócio — o API não sabe o que é `messages/partial`.
 */
// ui.js — handleStreamEvent

function handleStreamEvent(event, aiMsg) {
    const { type, data } = event;

    if (type === 'messages/partial') {
        let content = '';
        if (Array.isArray(data) && data.length > 0) {
            const item = data[0];
            if (typeof item === 'string')                   content = item;
            else if (item && item.content !== undefined)    content = item.content;
        } else if (data && data.content !== undefined) {
            content = data.content;
        } else if (typeof data === 'string') {
            content = data;
        }

        if (content) {
            aiMsg.content = content;
            updateLastMessageFast(content);
        }
        return;
    }

    if (type === 'values') {
        // O `values` traz a thread COMPLETA do servidor. NÃO substituir o store
        // local (IDs diferentes + mensagens antigas). Apenas sincronizar o
        // conteúdo final da IA que está em progresso.
        if (Array.isArray(data.messages) && data.messages.length > 0) {
            const latest = data.messages[data.messages.length - 1];
            if (latest && latest.type !== 'human' && latest.content !== undefined) {
                aiMsg.content = latest.content;
                updateLastMessage(latest.content, false);
            }
        }
        return;
    }

    if (type === 'error') {
        showToast('Erro: ' + (data.error || JSON.stringify(data)));
    }
}

// ============================================================
// 9. HANDLER DO FORM
// ============================================================
function handleSendMessage(event) {
    event.preventDefault();
    const text = inputEl.value.trim();
    if (!text) return;

    inputEl.value = '';
    inputEl.style.height = 'auto';
    sendUserMessage(text);
}

// ============================================================
// 10. BINDINGS
// ============================================================
if (inputEl) {
    inputEl.addEventListener('input', () => {
        if (!isStreaming) sendBtn.disabled = inputEl.value.trim() === '';
    });
}

window.onload = () => {
    renderMessages();
    checkConnection();

    const chatForm = document.getElementById('chat-form');
    if (chatForm) chatForm.addEventListener('submit', handleSendMessage);
};
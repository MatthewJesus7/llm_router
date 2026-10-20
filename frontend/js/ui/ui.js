// ui.js
// Orquestração da interface: estado, eventos, composer, toast, clipboard.
// Delega parsing para markdown.js e geração de DOM para render.js.

let renderedCount = 0;

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
// 2. COMPOSER / ESTADO DE STREAMING
// ============================================================
function setStreamingState(v) {
    if (typeof isStreaming !== 'undefined') isStreaming = v;
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
// 3. CLIPBOARD
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
// 4. SESSÃO
// ============================================================
function resetSession() {
    currentThreadId = crypto.randomUUID();
    messagesStore = [];
    renderedCount = 0;
    renderMessages();
    showToast('Nova conversa iniciada', 'ok');
}

// ============================================================
// 5. RENDER DO FEED
// ============================================================
function renderMessages() {
    if (typeof messagesStore === 'undefined') return;

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
// 6. ATUALIZAÇÃO DA ÚLTIMA MENSAGEM
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
    } else if (!content || content === '') {
        bubble.innerHTML = '<div class="typing"><span></span><span></span><span></span></div>';
    } else {
        Renderer.applyRichRendering(bubble, content, isFinished);
    }

    scrollIfNearBottom();
}

// ============================================================
// 7. ENVIO
// ============================================================
function handleSendMessage(event) {
    event.preventDefault();
    const text = inputEl.value.trim();
    if (!text) return;

    inputEl.value = '';
    inputEl.style.height = 'auto';

    if (typeof sendUserMessage === 'function') {
        sendUserMessage(text);
    }
}

// ============================================================
// 8. BINDINGS
// ============================================================
if (inputEl) {
    inputEl.addEventListener('input', () => {
        const isStreamingActive = typeof isStreaming !== 'undefined' ? isStreaming : false;
        if (!isStreamingActive) sendBtn.disabled = inputEl.value.trim() === '';
    });
}

window.onload = () => {
    renderMessages();
    if (typeof checkConnection === 'function') checkConnection();

    const chatForm = document.getElementById('chat-form');
    if (chatForm) chatForm.addEventListener('submit', handleSendMessage);
};
// ui.js (Atualizado: Substituição global iterativa para o bloco LaTeX)
let renderedCount = 0;
const inputEl = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const chatEl = document.getElementById('chat-messages');

if (window.marked && marked.setOptions) marked.setOptions({ breaks: true, gfm: true });

function showToast(msg, type = 'err') {
    const wrap = document.getElementById('toast');
    if (!wrap) return;
    const el = document.createElement('div');
    el.className = 'toast' + (type === 'ok' ? ' ok' : '');
    const ic = document.createElement('i');
    ic.className = type === 'ok' ? 'fa-solid fa-circle-check' : 'fa-solid fa-triangle-exclamation';
    const span = document.createElement('span');
    span.textContent = msg;
    el.append(ic, span);
    wrap.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateX(20px)'; setTimeout(() => el.remove(), 300); }, 3800);
}

function setStreamingState(v) {
    if (typeof isStreaming !== 'undefined') isStreaming = v;
    if (sendBtn && inputEl) {
        sendBtn.disabled = v || inputEl.value.trim() === '';
        sendBtn.innerHTML = v ? '<i class="fa-solid fa-spinner fa-spin text-xs"></i>' : '<i class="fa-solid fa-arrow-up text-xs"></i>';
    }
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

function fallbackCopy(text) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch (e) {}
    ta.remove();
}

function copyMsg(id, btn) {
    const m = messagesStore.find(x => x.id === id);
    if (!m) return;
    const text = typeof m.content === 'string' ? m.content : JSON.stringify(m.content, null, 2);
    const done = () => {
        btn.innerHTML = '<i class="fa-solid fa-check"></i>Copiado';
        showToast('Copiado para a área de transferência', 'ok');
        setTimeout(() => { btn.innerHTML = '<i class="fa-regular fa-copy"></i>Copiar'; }, 1600);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done).catch(() => { fallbackCopy(text); done(); });
    } else { fallbackCopy(text); done(); }
}

function resetSession() {
    currentThreadId = crypto.randomUUID();
    messagesStore = [];
    renderedCount = 0;
    renderMessages();
    showToast('Nova conversa iniciada', 'ok');
}

// Processamento seguro de conteúdo (protege tags incompletas durante o streaming)
function processRichContent(content, isFinished = false) {
    if (!content) return '';

    let parsedHtml = '';
    
    if (typeof content === 'object') {
        if (content.type === 'image' || content.url) {
            parsedHtml = `<div class="my-2"><img src="${content.url || content.src}" alt="${content.alt || 'Mídia'}" class="rounded-lg max-w-full shadow-md" />${content.caption ? `<p class="text-xs text-zinc-400 mt-1">${content.caption}</p>` : ''}</div>`;
        } else {
            parsedHtml = `<pre class="bg-zinc-900 p-3 rounded text-xs overflow-x-auto"><code>${JSON.stringify(content, null, 2)}</code></pre>`;
        }
    } else {
        let safeContent = content;

        // Iterar sobre todas as ocorrências de documentos LaTeX (\documentclass) no texto
        if (safeContent.includes('\\documentclass')) {
            safeContent = safeContent.replace(/\\documentclass[\s\S]*?\\begin\{document\}([\s\S]*?)\\end\{document\}/g, (match, docBody) => {
                return docBody
                    .replace(/\\textbf\{([^}]+)\}/g, '**$1**')
                    .replace(/\\begin\{itemize\}/g, '')
                    .replace(/\\end\{itemize\}/g, '')
                    .replace(/\\item/g, '*')
                    .replace(/\\begin\{align\*?\}/g, '$$\n\\begin{aligned}') .replace(/\\end\{align\*?\}/g, '\\end{aligned}\n$$');
            });
        }

        // Tenta parsear via Marked com segurança contra tags cortadas no fim do chunk
        try {
            parsedHtml = marked.parse(safeContent);
        } catch (e) {
            // Fallback se o marked falhar por tag incompleta no meio do stream
            parsedHtml = `<p>${safeContent.replace(/\n/g, '<br>')}</p>`;
        }

        parsedHtml = parsedHtml.replace(/\[img:(.*?)(?:\Vert{}(.*?))?\]/g, (match, url, caption) => {
            return `<div class="my-3"><img src="${url.trim()}" class="rounded-lg max-w-full shadow-md" />${caption ? `<p class="text-xs text-zinc-400 mt-1">${caption.trim()}</p>` : ''}</div>`;
        });
    }

    return parsedHtml;
}

function applyRichRendering(bubbleElement, content, isFinished = false) {
    if (!content || content === '') {
        bubbleElement.innerHTML = '<div class="typing"><span></span><span></span><span></span></div>';
        return;
    }

    bubbleElement.innerHTML = processRichContent(content, isFinished);

    const tryRenderMath = (retries = 5) => {
        if (typeof renderMathInElement === 'function') {
            try {
                renderMathInElement(bubbleElement, {
                    delimiters: [
                        {left: '$$', right: '$$', display: true},
                        {left: '$', right: '$', display: false},
                        {left: '\\(', right: '\\)', display: false},
                        {left: '[', right: ']', display: true}
                    ],
                    throwOnError: false
                });
            } catch (e) {
                // Silencia erros temporários de LaTeX incompleto durante o streaming
            }
        } else if (retries > 0) {
            setTimeout(() => tryRenderMath(retries - 1), 150);
        }
    };

    tryRenderMath();
}

function createMessageElement(msg) {
    const isUser = msg.type === 'human';
    const textContent = typeof msg.content === 'string' ? msg.content : (typeof msg.content === 'object' ? msg.content : JSON.stringify(msg.content));

    const row = document.createElement('div');
    row.className = `msg-row flex items-start gap-2.5 max-w-3xl mx-auto w-full ${isUser ? 'justify-end' : 'justify-start'} msg`;
    row.dataset.id = msg.id;

    const avatar = document.createElement('div');
    avatar.className = `avatar ${isUser ? 'avatar-user' : 'avatar-ai'}`;
    avatar.innerHTML = isUser ? '<i class="fa-solid fa-user text-[10px]"></i>' : '<i class="fa-solid fa-wand-magic-sparkles text-[10px]"></i>';

    const contentDiv = document.createElement('div');
    contentDiv.className = `flex flex-col ${isUser ? 'items-end' : 'items-start'} max-w-[85%] sm:max-w-[75%]`;

    const bubble = document.createElement('div');
    bubble.className = `bubble ${isUser ? 'bubble-user' : 'bubble-ai markdown-body'} px-4 py-3 text-sm`;
    bubble.id = `bubble-${msg.id}`;

    if (isUser) {
        bubble.textContent = typeof textContent === 'string' ? textContent : JSON.stringify(textContent);
    } else {
        applyRichRendering(bubble, textContent, true);
    }

    contentDiv.appendChild(bubble);

    if (!isUser && textContent !== '') {
        const actions = document.createElement('div');
        actions.className = 'msg-actions';
        actions.innerHTML = `<button class="copy-btn" onclick="copyMsg('${msg.id}',this)"><i class="fa-regular fa-copy"></i>Copiar</button>`;
        contentDiv.appendChild(actions);
    }

    if (isUser) {
        row.appendChild(contentDiv);
        row.appendChild(avatar);
    } else {
        row.appendChild(avatar);
        row.appendChild(contentDiv);
    }

    return row;
}

function renderMessages() {
    if (typeof messagesStore === 'undefined') return;

    if (messagesStore.length === 0) {
        renderedCount = 0;
        chatEl.innerHTML = `
            <div class="flex flex-col items-center justify-center h-full text-center px-4 fade-in">
                <div class="relative mb-5">
                    <div class="absolute -inset-3 rounded-[28px] bg-gradient-to-tr from-indigo-600/40 to-fuchsia-600/40 blur-2xl"></div>
                    <div class="relative w-16 h-16 rounded-3xl bg-white/5 border border-white/10 flex items-center justify-center">
                        <i class="fa-solid fa-wand-magic-sparkles text-xl bg-gradient-to-tr from-indigo-300 to-fuchsia-300 bg-clip-text text-transparent"></i>
                    </div>
                </div>
                <h2 class="text-xl font-bold tracking-tight text-white">Como posso ajudar?</h2>
                <p class="text-sm text-zinc-500 mt-2 max-w-sm leading-relaxed">Envie uma mensagem para conversar com o modelo configurado no seu backend.</p>
                <div class="flex flex-wrap justify-center gap-2.5 mt-7 max-w-md">
                    <button class="chip" data-p="Explique de forma simples como funciona uma rede neural." onclick="usePrompt(this.dataset.p)"><i class="fa-solid fa-brain"></i>Explicar um conceito</button>
                    <button class="chip" data-p="Me ajude a escrever um e-mail profissional e objetivo." onclick="usePrompt(this.dataset.p)"><i class="fa-solid fa-paper-plane"></i>Escrever um e-mail</button>
                    <button class="chip" data-p="Faça um brainstorm com 10 ideias criativas para um projeto pessoal." onclick="usePrompt(this.dataset.p)"><i class="fa-solid fa-lightbulb"></i>Brainstorm de ideias</button>
                </div>
            </div>`;
        return;
    }

    if (renderedCount === 0) {
        chatEl.innerHTML = '';
    }

    const fragment = document.createDocumentFragment();
    for (let i = renderedCount; i < messagesStore.length; i++) {
        fragment.appendChild(createMessageElement(messagesStore[i]));
    }
    
    if (fragment.childNodes.length > 0) {
        chatEl.appendChild(fragment);
    }

    renderedCount = messagesStore.length;
    chatEl.scrollTop = chatEl.scrollHeight;
}

function updateLastMessageFast(content) {
    if (messagesStore.length === 0) return;
    const lastMsg = messagesStore[messagesStore.length - 1];
    lastMsg.content = content;

    const bubble = document.getElementById(`bubble-${lastMsg.id}`);
    if (bubble) {
        applyRichRendering(bubble, content, false);
    } else {
        renderMessages();
    }

    const isNearBottom = chatEl.scrollHeight - chatEl.scrollTop - chatEl.clientHeight < 120;
    if (isNearBottom) {
        chatEl.scrollTop = chatEl.scrollHeight;
    }
}

function updateLastMessage(content, isFinished = true) {
    if (messagesStore.length === 0) return;
    const lastMsg = messagesStore[messagesStore.length - 1];
    lastMsg.content = content;

    const bubble = document.getElementById(`bubble-${lastMsg.id}`);
    if (bubble) {
        if (!content || content === '') {
            bubble.innerHTML = '<div class="typing"><span></span><span></span><span></span></div>';
        } else {
            applyRichRendering(bubble, content, isFinished);
        }
    } else {
        renderMessages();
    }

    const isNearBottom = chatEl.scrollHeight - chatEl.scrollTop - chatEl.clientHeight < 120;
    if (isNearBottom) {
        chatEl.scrollTop = chatEl.scrollHeight;
    }
}

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
    if (chatForm) {
        chatForm.addEventListener('submit', handleSendMessage);
    }
};
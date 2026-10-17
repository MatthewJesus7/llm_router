// ui.js (Otimizado contra travamentos de CPU)
let renderedCount = 0;
const inputEl = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const chatEl = document.getElementById('chat-messages');

if (window.marked && marked.setOptions) marked.setOptions({ breaks: true, gfm: true });

function showToast(msg, type = 'err') {
    const wrap = document.getElementById('toast');
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
    isStreaming = v;
    sendBtn.disabled = v || inputEl.value.trim() === '';
    sendBtn.innerHTML = v ? '<i class="fa-solid fa-spinner fa-spin text-xs"></i>' : '<i class="fa-solid fa-arrow-up text-xs"></i>';
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

// Cria o elemento DOM de uma mensagem individual
function createMessageElement(msg) {
    const isUser = msg.type === 'human';
    const textContent = typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content);

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
        bubble.textContent = textContent;
    } else if (textContent === '') {
        bubble.innerHTML = '<div class="typing"><span></span><span></span><span></span></div>';
    } else {
        bubble.innerHTML = marked.parse(textContent);
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

// Renderização inteligente: Só limpa se o chat esvaziou; caso contrário, adiciona incrementalmente
function renderMessages() {
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

    // Se havia o estado vazio, removemos ele antes de injetar as mensagens reais
    if (renderedCount === 0) {
        chatEl.innerHTML = '';
    }

    // Renderiza apenas as novas mensagens que entraram no array
    const fragment = document.createDocumentFragment();
    for (let i = renderedCount; i < messagesStore.length; i++) {
        fragment.appendChild(createMessageElement(messagesStore[i]));
    }
    
    if (fragment.childNodes.length > 0) {
        chatEl.appendChild(fragment);
    }

    renderedCount = messagesStore.length;
    chatEl.scrollTo({ top: chatEl.scrollHeight, behavior: isStreaming ? 'auto' : 'smooth' });
}

// Atualização cirúrgica focada apenas no último balão (usada durante o stream para zero lag)
function updateLastMessage(content) {
    if (messagesStore.length === 0) return;
    const lastMsg = messagesStore[messagesStore.length - 1];
    lastMsg.content = content;

    const bubble = document.getElementById(`bubble-${lastMsg.id}`);
    if (bubble) {
        bubble.innerHTML = content === '' ? '<div class="typing"><span></span><span></span><span></span></div>' : marked.parse(content);
    }
    chatEl.scrollTo({ top: chatEl.scrollHeight, behavior: 'auto' });
}

function handleSendMessage(event) {
    event.preventDefault();
    const text = inputEl.value.trim();
    if (!text) return;
    inputEl.value = '';
    inputEl.style.height = 'auto';
    sendUserMessage(text);
}

inputEl.addEventListener('input', () => {
    if (!isStreaming) sendBtn.disabled = inputEl.value.trim() === '';
});

window.onload = () => {
    renderMessages();
    checkConnection();
    document.getElementById('chat-form').addEventListener('submit', handleSendMessage);
};
// api.js (Transparente e Flexível: aceita texto, objetos estruturados, arrays ou multimídia sem filtragem severa)
const BASE_URL = "http://localhost:8000";
let currentThreadId = crypto.randomUUID();
let messagesStore = [];
let isStreaming = false;

async function checkConnection() {
    const dotEl = document.getElementById('connection-dot');
    const textEl = document.getElementById('connection-text');
    const selectEl = document.getElementById('provider-select');

    if (dotEl) dotEl.className = 'status-dot wait';
    if (textEl) textEl.textContent = 'Conectando...';

    try {
        const infoRes = await fetch(`${BASE_URL}/info`);
        if (!infoRes.ok) throw new Error('Falha ao conectar');
        const infoData = await infoRes.json();

        if (dotEl) dotEl.className = 'status-dot ok';
        if (textEl) textEl.textContent = 'Conectado';

        if (selectEl) {
            selectEl.innerHTML = '';
            if (infoData.providers && infoData.providers.length > 0) {
                infoData.providers.forEach(p => {
                    const opt = document.createElement('option');
                    opt.value = p;
                    opt.textContent = p;
                    selectEl.appendChild(opt);
                });
            } else {
                selectEl.innerHTML = '<option value="">Padrão do sistema</option>';
            }
        }
    } catch (err) {
        if (dotEl) dotEl.className = 'status-dot err';
        if (textEl) textEl.textContent = 'Desconectado';
        showToast('Não foi possível conectar ao servidor (' + BASE_URL + ')');
        console.error(err);
    }
}

async function sendUserMessage(text) {
    if (isStreaming) return;
    if (!text.trim()) return;

    setStreamingState(true);
    messagesStore.push({ id: crypto.randomUUID(), type: 'human', content: text });
    renderMessages();

    const providerEl = document.getElementById('provider-select');
    const provider = providerEl ? providerEl.value : '';

    try {
        const response = await fetch(`${BASE_URL}/threads/${currentThreadId}/runs/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                provider_name: provider,
                input: { messages: messagesStore }
            })
        });

        if (!response.ok) {
            const errJson = await response.json().catch(() => ({}));
            throw new Error(errJson.detail || 'Erro na comunicação com o servidor');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        const aiMsg = { id: crypto.randomUUID(), type: 'ai', content: '' };
        messagesStore.push(aiMsg);
        renderMessages();

        let lastRenderTime = 0;
        const RENDER_THROTTLE_MS = 16.6;

        while (true) {
            const { value, done } = await reader.read();
            
            if (done) {
                if (buffer.trim()) {
                    processChunks(buffer, aiMsg);
                }
                break;
            }

            buffer += decoder.decode(value, { stream: true });
            const events = buffer.split('\n\n');
            buffer = events.pop(); 

            for (const eventBlock of events) {
                processChunks(eventBlock, aiMsg);
            }

            const now = performance.now();
            if (now - lastRenderTime > RENDER_THROTTLE_MS) {
                lastRenderTime = now;
                if (typeof updateLastMessageFast === 'function') {
                    updateLastMessageFast(aiMsg.content);
                }
            }
        }

        updateLastMessage(aiMsg.content, true);

    } catch (err) {
        showToast('Erro ao enviar mensagem: ' + err.message);
        const last = messagesStore[messagesStore.length - 1];
        if (last && last.type === 'ai' && !last.content) {
            messagesStore.pop();
            renderMessages();
        }
    } finally {
        setStreamingState(false);
    }
}

// Processador ultra permissivo de blocos SSE: aceita qualquer payload bruto (strings, objetos, multimídia)
function processChunks(eventBlock, aiMsg) {
    if (!eventBlock.trim()) return;

    let eventType = 'message';
    let dataLines = [];

    const lines = eventBlock.split('\n');
    for (const line of lines) {
        if (line.startsWith('event:')) {
            eventType = line.substring(6).trim();
        } else if (line.startsWith('data:') || line.startsWith('data: ')) {
            const prefixLength = line.startsWith('data: ') ? 6 : 5;
            dataLines.push(line.substring(prefixLength));
        }
    }

    if (dataLines.length === 0) return;
    const dataPayload = dataLines.join('\n');

    try {
        const parsedData = JSON.parse(dataPayload);

        if (eventType === 'messages/partial') {
            if (Array.isArray(parsedData) && parsedData.length > 0) {
                // Aceita string, objetos estruturados ou arrays multimídia inteiros
                aiMsg.content = parsedData[0].content !== undefined ? parsedData[0].content : parsedData[0];
            } else {
                aiMsg.content = parsedData.content !== undefined ? parsedData.content : parsedData;
            }
        } else if (eventType === 'values') {
            if (parsedData.messages) {
                messagesStore = parsedData.messages;
                if (messagesStore.length > 0) {
                    const latest = messagesStore[messagesStore.length - 1];
                    if (latest && latest.content !== undefined) {
                        aiMsg.content = latest.content;
                    }
                }
                renderMessages();
            } else {
                aiMsg.content = parsedData;
            }
        } else if (eventType === 'error') {
            showToast('Erro: ' + (parsedData.error || JSON.stringify(parsedData)));
        } else {
            // Eventos customizados ou desconhecidos: repassa o dado cru para o UI tratar
            aiMsg.content = parsedData.content !== undefined ? parsedData.content : parsedData;
        }
    } catch (parseErr) {
        // Se o payload não for JSON válido, assume que é texto cru em streaming e acumula
        if (aiMsg.content && typeof aiMsg.content === 'string') {
            aiMsg.content += dataPayload;
        } else {
            aiMsg.content = dataPayload;
        }
    }
}
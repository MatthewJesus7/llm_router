// api.js (Correção definitiva do parser SSE e renderização)
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

        while (true) {
            const { value, done } = await reader.read();
            
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            
            // Separa os blocos SSE por linha dupla
            const events = buffer.split(/\r?\n\r?\n/);
            buffer = events.pop(); // Mantém o último pedaço incompleto no buffer

            for (const eventBlock of events) {
                processChunks(eventBlock, aiMsg);
            }
        }

        // Processa qualquer sobra final no buffer
        if (buffer.trim()) {
            processChunks(buffer, aiMsg);
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

function processChunks(eventBlock, aiMsg) {
    if (!eventBlock.trim()) return;

    let eventType = 'message';
    let dataLines = [];

    const lines = eventBlock.split(/\r?\n/);
    for (const line of lines) {
        if (line.startsWith('event:')) {
            eventType = line.substring(6).trim();
        } else if (line.startsWith('data:')) {
            dataLines.push(line.substring(5).trimStart());
        }
    }

    if (dataLines.length === 0) return;
    const dataPayload = dataLines.join('\n');

    try {
        const parsedData = JSON.parse(dataPayload);

        if (eventType === 'messages/partial') {
            if (Array.isArray(parsedData) && parsedData.length > 0) {
                const item = parsedData[0];
                if (typeof item === 'string') {
                    aiMsg.content = item;
                } else if (item && item.content !== undefined) {
                    aiMsg.content = item.content;
                }
            } else if (parsedData && parsedData.content !== undefined) {
                aiMsg.content = parsedData.content;
            } else if (typeof parsedData === 'string') {
                aiMsg.content = parsedData;
            }
            
            // Força a atualização imediata da UI a cada chunk recebido
            if (aiMsg.content) {
                if (typeof updateLastMessageFast === 'function') {
                    updateLastMessageFast(aiMsg.content);
                } else {
                    updateLastMessage(aiMsg.content, false);
                }
            }
        } else if (eventType === 'values') {
            if (parsedData.messages) {
                messagesStore = parsedData.messages;
                const latest = messagesStore[messagesStore.length - 1];
                if (latest && latest.content !== undefined) {
                    aiMsg.content = latest.content;
                }
                renderMessages();
            }
        } else if (eventType === 'error') {
            showToast('Erro: ' + (parsedData.error || JSON.stringify(parsedData)));
        }
    } catch (parseErr) {
        // Fallback caso venha texto puro sem JSON válido
        if (dataPayload) {
            aiMsg.content = dataPayload;
            if (typeof updateLastMessageFast === 'function') {
                updateLastMessageFast(aiMsg.content);
            }
        }
    }
}
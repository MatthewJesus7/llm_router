// api.js (Transparente: entrega tudo cru e completo para o ui.js gerenciar)
const BASE_URL = "http://localhost:8000";
let currentThreadId = crypto.randomUUID();
let messagesStore = [];
let isStreaming = false;

async function checkConnection() {
    const dotEl = document.getElementById('connection-dot');
    const textEl = document.getElementById('connection-text');
    const selectEl = document.getElementById('provider-select');

    dotEl.className = 'status-dot wait';
    textEl.textContent = 'Conectando...';

    try {
        const infoRes = await fetch(`${BASE_URL}/info`);
        if (!infoRes.ok) throw new Error('Falha ao conectar');
        const infoData = await infoRes.json();

        dotEl.className = 'status-dot ok';
        textEl.textContent = 'Conectado';

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
    } catch (err) {
        dotEl.className = 'status-dot err';
        textEl.textContent = 'Desconectado';
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

    const provider = document.getElementById('provider-select').value;

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
                // Se sobrou algo no buffer no fechamento da conexão, processa à força
                if (buffer.trim()) {
                    processChunks(buffer, aiMsg);
                }
                break;
            }

            buffer += decoder.decode(value, { stream: true });
            const events = buffer.split('\n\n');
            buffer = events.pop(); // Guarda o fragmento pendente

            for (const eventBlock of events) {
                processChunks(eventBlock, aiMsg);
            }

            // Throttle de UI leve para manter o FPS da CPU velha em pé
            const now = performance.now();
            if (now - lastRenderTime > RENDER_THROTTLE_MS) {
                lastRenderTime = now;
                if (typeof updateLastMessageFast === 'function') {
                    updateLastMessageFast(aiMsg.content);
                }
            }
        }

        // Entrega final garantida e sem cortes ao ui.js
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

// Processador bruto de blocos SSE (Joga toda a responsabilidade de exibição para o ui.js)
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
                // Atribuição direta e sem filtros de tamanho
                aiMsg.content = parsedData[0].content || '';
            }
        } else if (eventType === 'values') {
            if (parsedData.messages) {
                messagesStore = parsedData.messages;
                if (messagesStore.length > 0) {
                    const latest = messagesStore[messagesStore.length - 1];
                    if (latest && latest.content) {
                        aiMsg.content = latest.content;
                    }
                }
                renderMessages();
            }
        } else if (eventType === 'error') {
            showToast('Erro: ' + (parsedData.error || JSON.stringify(parsedData)));
        }
    } catch (parseErr) {
        // Se der erro no JSON, joga no console mas não interrompe o fluxo bruto
        console.warn('Payload parcial ignorado ou bruto:', dataPayload);
    }
}
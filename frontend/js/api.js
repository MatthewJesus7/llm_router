// api.js (Corrigido para parser robusto de SSE e exibição garantida)
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
        renderMessages(); // Cria o balão inicial com o indicador de digitação

        let currentEvent = 'message';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const events = buffer.split('\n\n');
            buffer = events.pop(); // Mantém o evento incompleto no buffer

            for (const eventBlock of events) {
                if (!eventBlock.trim()) continue;

                let eventType = 'message';
                let dataLines = [];

                const lines = eventBlock.split('\n');
                for (const line of lines) {
                    if (line.startsWith('event:')) {
                        eventType = line.substring(6).trim();
                    } else if (line.startsWith('data:') || line.startsWith('data: ')) {
                        // Captura o restante da linha independentemente de haver espaço extra
                        const prefixLength = line.startsWith('data: ') ? 6 : 5;
                        dataLines.push(line.substring(prefixLength));
                    }
                }

                if (dataLines.length === 0) continue;
                const dataPayload = dataLines.join('\n');

                try {
                    const parsedData = JSON.parse(dataPayload);

                    if (eventType === 'messages/partial') {
                        if (Array.isArray(parsedData) && parsedData.length > 0) {
                            aiMsg.content = parsedData[0].content || '';
                            updateLastMessage(aiMsg.content);
                        }
                    } else if (eventType === 'values') {
                        if (parsedData.messages) {
                            messagesStore = parsedData.messages;
                            renderMessages();
                        }
                    } else if (eventType === 'error') {
                        showToast('Erro: ' + (parsedData.error || JSON.stringify(parsedData)));
                    }
                } catch (parseErr) {
                    console.error('Erro ao decodificar JSON do SSE:', parseErr, dataPayload);
                }
            }
        }
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
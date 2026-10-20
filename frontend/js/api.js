// api.js
// Camada de transporte. Não conhece DOM, estado ou UI.
// Único arquivo com permissão de tocar em fetch / BASE_URL.

(function (global) {
    'use strict';

    const BASE_URL = 'http://localhost:8000';

    // ============================================================
    // INFO / CONEXÃO
    // ============================================================
    /**
     * Consulta o /info do backend.
     * Nunca lança — devolve sempre um resultado discriminado.
     *
     * @returns {Promise<{ ok: true, providers: string[] }
     *                 | { ok: false, error: Error, baseUrl: string }>}
     */
    async function fetchInfo() {
        try {
            const res = await fetch(`${BASE_URL}/info`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            return { ok: true, providers: Array.isArray(data.providers) ? data.providers : [] };
        } catch (error) {
            return { ok: false, error, baseUrl: BASE_URL };
        }
    }

    // ============================================================
    // STREAMING
    // ============================================================
    /**
     * Executa um run e emite eventos SSE um a um.
     * Não interpreta o conteúdo — só entrega `{ type, data }`.
     *
     * @param {Object}          opts
     * @param {string}          opts.threadId
     * @param {string}          opts.provider
     * @param {Array}           opts.messages
     * @param {AbortSignal}     [opts.signal]
     *
     * @yields {{ type: string, data: any }}
     */
    async function* streamRun({ threadId, provider, messages, signal }) {
        const response = await fetch(`${BASE_URL}/threads/${threadId}/runs/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                provider_name: provider,
                input: { messages },
            }),
            signal,
        });

        if (!response.ok) {
            const errJson = await response.json().catch(() => ({}));
            throw new Error(errJson.detail || `HTTP ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            // SSE: blocos separados por linha em branco
            const blocks = buffer.split(/\r?\n\r?\n/);
            buffer = blocks.pop(); // último bloco pode estar incompleto

            for (const block of blocks) {
                const evt = parseSSEBlock(block);
                if (evt) yield evt;
            }
        }

        // sobra final
        if (buffer.trim()) {
            const evt = parseSSEBlock(buffer);
            if (evt) yield evt;
        }
    }

    /**
     * Parse de um bloco SSE bruto em `{ type, data }`.
     * Aceita JSON inválido e devolve a string crua em `data` (fallback).
     */
    function parseSSEBlock(block) {
        if (!block.trim()) return null;

        let eventType = 'message';
        const dataLines = [];

        for (const line of block.split(/\r?\n/)) {
            if (line.startsWith('event:')) {
                eventType = line.substring(6).trim();
            } else if (line.startsWith('data:')) {
                dataLines.push(line.substring(5).trimStart());
            }
        }

        if (dataLines.length === 0) return null;

        const payload = dataLines.join('\n');
        try {
            return { type: eventType, data: JSON.parse(payload) };
        } catch (e) {
            return { type: eventType, data: payload };
        }
    }

    global.API = { fetchInfo, streamRun, BASE_URL };
})(window);
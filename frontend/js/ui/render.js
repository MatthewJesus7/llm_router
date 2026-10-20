// render.js
// Geração de HTML no DOM: mensagens, bubbles, estado vazio, KaTeX.
// Sem classes utilitárias Tailwind — apenas classes semânticas (content.css).

(function (global) {
    'use strict';

    const KATEX_DELIMITERS = [
        { left: '$$', right: '$$', display: true },
        { left: '$',  right: '$',  display: false },
        { left: '\\(', right: '\\)', display: false },
        { left: '\\[', right: '\\]', display: true },
    ];

    /**
     * Aplica processRichContent + renderização KaTeX num bubble já existente.
     */
    function applyRichRendering(bubbleElement, content, isFinished = false) {
        if (!content || content === '') {
            bubbleElement.innerHTML = '<div class="typing"><span></span><span></span><span></span></div>';
            return;
        }

        bubbleElement.innerHTML = MarkdownRenderer.processRichContent(content, isFinished);
        renderMathWithRetry(bubbleElement);
    }

    /**
     * Tenta rodar KaTeX no elemento. Se o auto-render ainda não carregou,
     * tenta de novo até `retries` vezes.
     */
    function renderMathWithRetry(el, retries = 5) {
        if (typeof renderMathInElement === 'function') {
            try {
                renderMathInElement(el, {
                    delimiters: KATEX_DELIMITERS,
                    throwOnError: false,
                });
            } catch (e) {
                // LaTeX incompleto durante streaming — ignora silenciosamente
            }
            return;
        }
        if (retries > 0) {
            setTimeout(() => renderMathWithRetry(el, retries - 1), 150);
        }
    }

    /**
     * Cria o nó DOM de uma mensagem (avatar + bubble + ações).
     */
    function createMessageElement(msg, onCopy) {
        const isUser = msg.type === 'human';
        const textContent = typeof msg.content === 'string'
            ? msg.content
            : (typeof msg.content === 'object' ? msg.content : JSON.stringify(msg.content));

        // linha
        const row = document.createElement('div');
        row.className = 'msg-row ' + (isUser ? 'msg-row--user' : 'msg-row--ai');
        row.dataset.id = msg.id;

        // avatar
        const avatar = document.createElement('div');
        avatar.className = 'avatar ' + (isUser ? 'avatar-user' : 'avatar-ai');
        avatar.innerHTML = isUser
            ? '<i class="fa-solid fa-user"></i>'
            : '<i class="fa-solid fa-wand-magic-sparkles"></i>';

        // coluna de conteúdo
        const contentDiv = document.createElement('div');
        contentDiv.className = 'msg-content' + (isUser ? ' msg-content--user' : '');

        // bubble
        const bubble = document.createElement('div');
        bubble.className = 'bubble ' + (isUser ? 'bubble-user' : 'bubble-ai markdown-body');
        bubble.id = 'bubble-' + msg.id;

        if (isUser) {
            bubble.textContent = typeof textContent === 'string'
                ? textContent
                : JSON.stringify(textContent);
        } else {
            applyRichRendering(bubble, textContent, true);
        }

        contentDiv.appendChild(bubble);

        // botão copiar (só AI, e só se há conteúdo)
        if (!isUser && textContent !== '') {
            const actions = document.createElement('div');
            actions.className = 'msg-actions';

            const btn = document.createElement('button');
            btn.className = 'copy-btn';
            btn.innerHTML = '<i class="fa-regular fa-copy"></i>Copiar';
            btn.addEventListener('click', () => onCopy(msg.id, btn));

            actions.appendChild(btn);
            contentDiv.appendChild(actions);
        }

        // ordem visual
        if (isUser) {
            row.appendChild(contentDiv);
            row.appendChild(avatar);
        } else {
            row.appendChild(avatar);
            row.appendChild(contentDiv);
        }

        return row;
    }

    /**
     * HTML do estado vazio (tela inicial). Recebe `onPrompt` injetado por ui.js.
     */
    function createEmptyStateElement(onPrompt) {
        const wrap = document.createElement('div');
        wrap.className = 'empty-state fade-in';

        wrap.innerHTML = `
            <div class="empty-icon-wrap">
                <div class="empty-icon-glow"></div>
                <div class="empty-icon">
                    <i class="fa-solid fa-wand-magic-sparkles"></i>
                </div>
            </div>
            <h2 class="empty-title">Como posso ajudar?</h2>
            <p class="empty-subtitle">Envie uma mensagem para conversar com o modelo configurado no seu backend.</p>
            <div class="chips">
                <button class="chip" data-p="Explique de forma simples como funciona uma rede neural.">
                    <i class="fa-solid fa-brain"></i>Explicar um conceito
                </button>
                <button class="chip" data-p="Me ajude a escrever um e-mail profissional e objetivo.">
                    <i class="fa-solid fa-paper-plane"></i>Escrever um e-mail
                </button>
                <button class="chip" data-p="Faça um brainstorm com 10 ideias criativas para um projeto pessoal.">
                    <i class="fa-solid fa-lightbulb"></i>Brainstorm de ideias
                </button>
            </div>`;

        wrap.querySelectorAll('.chip').forEach(chip => {
            chip.addEventListener('click', () => onPrompt(chip.dataset.p));
        });

        return wrap;
    }

    global.Renderer = {
        applyRichRendering,
        createMessageElement,
        createEmptyStateElement,
    };
})(window);
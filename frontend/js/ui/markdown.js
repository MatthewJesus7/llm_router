// markdown.js
// Parsing de conteúdo rico: markdown, documentos LaTeX, imagens e objetos.
// Nenhuma dependência de DOM. Exporta funções puras no escopo global.

(function (global) {
    'use strict';

    if (global.marked && marked.setOptions) {
        marked.setOptions({ breaks: true, gfm: true });
    }

    /**
     * Converte o corpo de um documento LaTeX (\documentclass...\end{document})
     * em markdown equivalente, para que o `marked` consiga processar.
     */
    function latexDocumentToMarkdown(text) {
        if (!text.includes('\\documentclass')) return text;

        return text.replace(
            /\\documentclass[\s\S]*?\\begin\{document\}([\s\S]*?)\\end\{document\}/g,
            (match, docBody) => {
                return docBody
                    .replace(/\\textbf\{([^}]+)\}/g, '**$1**')
                    .replace(/\\begin\{itemize\}/g, '')
                    .replace(/\\end\{itemize\}/g, '')
                    .replace(/\\item/g, '*')
                    .replace(/\\begin\{align\*?\}/g, '$$\n\\begin{aligned}')
                    .replace(/\\end\{align\*?\}/g, '\\end{aligned}\n$$');
            }
        );
    }

    // trechos alterados de markdown.js

    function expandImageMarkers(html) {
        return html.replace(/\[img:(.*?)(?:\Vert{}(.*?))?\]/g, (match, url, caption) => {
            const cap = caption
                ? `<p class="md-img-caption">${caption.trim()}</p>`
                : '';
            return `<div class="md-img-wrap"><img src="${url.trim()}" class="md-img" alt="" />${cap}</div>`;
        });
    }

    function objectContentToHtml(content) {
        if (content.type === 'image' || content.url) {
            const caption = content.caption
                ? `<p class="md-img-caption">${content.caption}</p>`
                : '';
            return `<div class="md-img-wrap"><img src="${content.url || content.src}" alt="${content.alt || 'Mídia'}" class="md-img" />${caption}</div>`;
        }
        return `<pre class="md-json"><code>${JSON.stringify(content, null, 2)}</code></pre>`;
    }

    /**
     * Entrada principal: recebe qualquer `content` (string ou objeto)
     * e devolve HTML renderizado. Não mexe em LaTeX inline (isso é feito depois
     * pelo KaTeX, em render.js).
     */
    function processRichContent(content, isFinished = false) {
        if (!content) return '';

        if (typeof content === 'object') {
            return objectContentToHtml(content);
        }

        const safe = latexDocumentToMarkdown(content);

        let html;
        try {
            html = marked.parse(safe);
        } catch (e) {
            // chunk cortado no meio do stream: fallback simples
            html = `<p>${safe.replace(/\n/g, '<br>')}</p>`;
        }

        return expandImageMarkers(html);
    }

    global.MarkdownRenderer = {
        processRichContent,
        // helpers exportados para teste/reuso
        latexDocumentToMarkdown,
        expandImageMarkers,
        objectContentToHtml,
    };
})(window);
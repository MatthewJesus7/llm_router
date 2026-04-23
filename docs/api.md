# Projeto - Como Rodar

## Backend

```bash
cd sua_pasta_raiz
uvicorn app.llm_router.main:app --reload --port 8000
Estrutura de pastas esperada:
textraiz-do-projeto/
└── app/
    └── llm_router/

--host 0.0.0.0 → opcional (se quiser acessar pelo celular usando o IP da máquina)


Frontend
Bashcd agent-chat-ui
npm run dev
⚠️ Por enquanto só funciona em modo local.
npm run build está quebrando.

Configuração Inicial

Copie o arquivo .env.example para .env
Configure as variáveis de ambiente (a maioria é opcional)


Como Adicionar um Novo Provider

Abra ai_router.py
Adicione o provider + chave de API com o nome que quiser


Se Estiver Dando Erro

Provavelmente o formato da API do novo provider é diferente do que o backend espera.
Abra ai_builder.py e adicione o novo formato (leva poucos segundos).


Ajustes Gerais

Timeouts, modo de operação, etc. → edite ai_core.py
Formato de resposta (falta LaTeX, código, etc.) → edite ai_parsers.py
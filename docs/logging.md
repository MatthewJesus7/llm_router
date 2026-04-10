Logging

O sistema utiliza o módulo padrão logging do Python para observabilidade da execução.

Não é necessário setup adicional além da configuração no entrypoint.

🚀 Quick Start

Logging já é inicializado automaticamente no ai_router.py:

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

Para alterar comportamento, use .env:

LOG_ENABLED=true
LOG_LEVEL=DEBUG

Se quiser desativar completamente:

LOG_ENABLED=false
⚙️ Configuração (.env)
# liga/desliga logging
LOG_ENABLED=true

# níveis: DEBUG | INFO | WARNING | ERROR | CRITICAL
LOG_LEVEL=INFO
🔁 Fluxo de Logs no Sistema

O logging segue o fluxo real de execução do router:

1. ai_router.py (entrada do sistema)

Responsável por lifecycle:

inicialização do router
carregamento de providers
falhas críticas

Exemplo:

INFO  | Inicializando AI Router
INFO  | 1 provider(s) configurado(s)
INFO  | AI Router pronto
2. core.py (núcleo de execução)

Onde acontece a maior parte dos logs.

Eventos:

seleção de provider
tentativa de request
resposta HTTP
retry / fallback
rate limit / cooldown
falha total

Exemplo:

DEBUG | [GoogleAIStudio] tentativa 1
DEBUG | [GoogleAIStudio] status 429
WARNING | [GoogleAIStudio] rate limited (429)
DEBUG | [GoogleAIStudio] tentativa 2
INFO  | [GoogleAIStudio] sucesso
3. parsers.py (interpretação de resposta)

Logs apenas quando há desvio do fluxo esperado:

fallback de parsing
erro ao interpretar resposta
conteúdo bloqueado pelo provider

Exemplo:

WARNING | Resposta bloqueada pelo provider: SAFETY
DEBUG   | Fallback parser acionado
WARNING | Erro parse Google: estrutura inesperada
4. builders.py

Não possui logging.

Motivo:

funções puras
sem decisão ou estado
📊 Níveis de Log
Level	Quando aparece
DEBUG	fluxo interno (retry, seleção)
INFO	sucesso e inicialização
WARNING	erros recuperáveis
ERROR	falha operacional
CRITICAL	falha total
🧠 Como ler os logs

Logs seguem o fluxo real de execução:

tentativa → erro → fallback → sucesso

ou

tentativa → erro → retry → erro → falha total
⚠️ Boas práticas
Não logar dados sensíveis (API keys, payloads completos)
Evitar duplicação de logs
Usar DEBUG para investigação, não para produção
Manter logging fora de funções puras
✔ Resumo
Logging já funciona sem setup adicional
Controle via .env
Logs refletem decisões reais do sistema
Núcleo do logging está em core.py
# LLM Router

Engine leve para executar prompts em múltiplos providers de LLM com fallback automático e tolerância a falhas.

**~500 linhas. Zero dependência de vendor. Funciona com qualquer API.**

---

## Por que usar

Você chama `.ask()`. O router decide qual provider usar, lida com rate limit, retry e cooldown sozinho. Se um provider cair, o próximo assume. Você recebe uma string.

Não há orquestração inteligente, sem avaliação semântica — só execução resiliente.

---

## Instalação

```bash
git clone https://github.com/seu-usuario/llm-router.git
cd llm-router
pip install requests python-dotenv
```

Crie um `.env` na raiz:

```env
GOOGLE_API_KEY=your_key_here
```

---

## Uso

```python
from llms.ai_router import ai_router

response = ai_router.ask("Explain black holes")
print(response)
```

---

## Documentação

| Arquivo | Conteúdo |
|---|---|
| [`docs/START_HERE.md`](docs/START_HERE.md) | Setup, fluxo, providers e troubleshooting |
| [`docs/GUIDE.md`](docs/DOCS.md) | Referência completa do sistema |
| [`docs/logging.md`](docs/logging.md) | Configuração de logs |
| [`docs/all_code.md`](docs/all_code.md) | Todo o código em um lugar só |

---

## Providers suportados

Funciona com qualquer API que aceite JSON. Vem configurado com Google AI Studio (Gemini).  
Adicionar um segundo provider são ~10 linhas — veja [`docs/START_HERE.md`](docs/START_HERE.md).

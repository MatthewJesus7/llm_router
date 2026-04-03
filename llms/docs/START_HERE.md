# START HERE

Guia de início rápido. Para entender o sistema em profundidade, veja `README.md`.

---

## 1. Instale as dependências

```bash
pip install requests python-dotenv
```

---

## 2. Crie o `.env` na raiz do projeto

```env
# obrigatório
GOOGLE_API_KEY=your_key_here

# opcionais — os defaults já funcionam bem para a maioria dos casos
GOOGLE_USAGE_LIMIT=80        # máximo de requisições por janela de tempo
GOOGLE_WINDOW_S=60           # duração da janela em segundos
GOOGLE_TIMEOUT=60            # tempo máximo de espera por resposta (segundos)
GOOGLE_MAX_OUTPUT_TOKENS=8192
```

---

## 3. Confirme a estrutura de pastas

```
llms/
  ai_core.py
  ai_builders.py
  ai_parsers.py
  ai_router.py
.env
```

---

## 4. Use

```python
from llms.ai_router import ai_router

response = ai_router.ask("Explain black holes")
print(response)
```

Opcionalmente, passe `temperature`:

```python
response = ai_router.ask("Explain black holes", temperature=0.2)
```

---

## Como o fluxo funciona

```text
ai_router.ask(prompt)
  ↓
ProviderManager seleciona o próximo provider disponível
  ↓
AIProvider monta e envia a requisição HTTP
  ↓
Parser normaliza a resposta → str
  ↓
retorna string
```

Se um provider falhar (erro HTTP, timeout, rate limit), ele entra em cooldown
e o próximo da lista é tentado automaticamente. Você não precisa tratar isso.

---

## Adicionando um segundo provider

Abra `ai_router.py` e adicione dentro de `make_providers()`, no bloco marcado com comentário.  
O exemplo abaixo usa Groq, mas qualquer API estilo OpenAI segue o mesmo padrão:

```python
from llms.ai_builders import build_openai_style
from llms.ai_parsers import parse_json_text_response

providers.append(AIProvider(
    name="Groq",
    api_key_env="GROQ_API_KEY",          # adicione esta chave no .env
    endpoint="https://api.groq.com/openai/v1/chat/completions",
    make_headers=lambda key: {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    },
    build_payload=lambda prompt, temp: build_openai_style(prompt, temp, "llama3-8b-8192"),
    parse_response=parse_json_text_response,
    usage_limit=int(os.getenv("GROQ_USAGE_LIMIT", "60")),
    window_seconds=int(os.getenv("GROQ_WINDOW_S", "60")),
    timeout=30,
    model="llama3-8b-8192"
))
```

Com dois providers ativos, o router faz fallback automaticamente se um falhar.

---

## Troubleshooting

**`GOOGLE_API_KEY não definido`**  
O arquivo `.env` não foi encontrado ou a variável está faltando. Confirme que o `.env` está na raiz do projeto e que a chave está correta.

---

**`Todos providers falharam.`**  
Todos os providers configurados estão em cooldown ou retornando erro. Causas comuns:
- chave de API inválida ou expirada
- rate limit real do provider atingido (diferente do limite interno)
- sem conexão com a internet

Verifique os logs — cada falha é registrada com o provider e o status HTTP.

---

**Resposta vazia ou `[Blocked: ...]`**  
O provider retornou uma resposta, mas o conteúdo foi bloqueado pela política do modelo (ex: prompt considerado sensível). Reformule o prompt.

---

**Timeout frequente**  
Aumente `GOOGLE_TIMEOUT` no `.env`. O default é 60s, mas modelos maiores podem demorar mais em horários de pico.

---

**Provider ignorado mesmo com chave configurada**  
O provider só entra na rotação se a variável de ambiente correspondente (`api_key_env`) estiver definida no `.env` e não vazia. Verifique o nome exato da variável.
# LLM Router — Resilient Multi-Provider Execution Engine

## 0. O que é

Engine mínima para executar prompts em múltiplos providers de LLM com:

* fallback automático
* tolerância a falhas
* seleção baseada em estado (não semântica)
* convergência obrigatória em `str`

---

## 1. TL;DR

```python
from llms.ai_router import ai_router

response = ai_router.ask("Explain black holes")
print(response)
```

---

## 2. Princípios do sistema

* **Output sempre string**
* **Providers independentes**
* **Roteamento não depende do conteúdo**
* **Erro não interrompe, apenas altera estado**
* **Primeiro provider viável vence**

---

## 3. Setup

### 3.1 Instalar dependências

```bash
pip install requests python-dotenv
```

---

### 3.2 Variáveis de ambiente

```env
GOOGLE_API_KEY=your_key_here

# opcionais
GOOGLE_USAGE_LIMIT=80
GOOGLE_WINDOW_S=60
GOOGLE_TIMEOUT=60
GOOGLE_MAX_OUTPUT_TOKENS=8192
```

---

### 3.3 Estrutura esperada

```
llms/
  ai_core.py
  ai_builders.py
  ai_parsers.py
  ai_router.py
```

---

## 4. Fluxo completo

```text
input
 ↓
ProviderManager.ask()
 ↓
seleção de provider (estado)
 ↓
execução HTTP
 ↓
parse (normalização)
 ↓
string
```

---

## 5. Core

### 5.1 AIProvider

Representa um backend executável.

#### Responsabilidades

* construir request
* enviar request
* parsear resposta
* gerenciar estado local

---

### Estado interno

```python
used_count
window_start
usage_limit
window_seconds
exhausted_until
lock
```

---

### Regras

* respeita rate limit
* entra em cooldown em erro
* é thread-safe

---

### Métodos principais

#### `can_use()`

Verifica se o provider pode ser usado agora.

#### `send(prompt)`

Executa request HTTP.

#### `mark_usage()`

Atualiza consumo.

#### `force_exhaust(ttl)`

Remove temporariamente da rotação.

---

## 5.2 ProviderManager

Scheduler da engine.

---

### Estratégia

* round-robin
* skip de providers indisponíveis
* retry limitado

---

### Método principal

#### `ask(prompt)`

Loop:

```text
seleciona provider disponível
↓
tenta execução
↓
se sucesso → retorna
↓
se falha → penaliza provider
↓
repete
```

---

### Regras de erro

| Evento    | Ação             |
| --------- | ---------------- |
| 200 OK    | retorna resposta |
| 429       | cooldown médio   |
| 4xx/5xx   | cooldown curto   |
| Exception | cooldown mínimo  |

---

## 6. Parsers

Responsáveis por:

```text
Response heterogêneo → string
```

---

### Estratégia

1. caminhos conhecidos (Gemini/OpenAI-like)
2. fallback por padrões
3. busca recursiva no JSON
4. fallback final: `resp.text`

---

### Funções

* `parse_google_ai_response`
* `parse_json_text_response`

---

### Propriedade

Alta tolerância a mudanças de API
Baixa garantia semântica

---

## 7. Builders

Transformam:

```text
(prompt, temperature) → payload
```

---

### Tipos

#### (A) Declarativo

Retorna JSON payload

#### (B) Executável

Executa chamada e retorna string diretamente

---

### Observação importante

O sistema aceita ambos, desde que o retorno final seja `str`.

---

## 8. Router

Responsável por:

* carregar `.env`
* instanciar providers
* montar ProviderManager

---

### Uso

```python
from llms.ai_router import ai_router

ai_router.ask("Hello")
```

---

## 9. Comportamento emergente

O sistema:

* favorece providers saudáveis
* evita automaticamente providers instáveis
* se adapta sem histórico persistente
* nunca falha por erro isolado

---

## 10. Limitações

### 10.1 Sem avaliação de qualidade

```text
qualquer resposta válida = aceita
```

---

### 10.2 Sem roteamento por tarefa

```text
input não influencia escolha
```

---

### 10.3 Dependência de pelo menos 1 provider funcional

Caso contrário:

```python
RuntimeError("Todos providers falharam.")
```

---

## 11. Extensões (sem quebrar o design)

---

### 11.1 Adicionar provider

```python
providers.append(AIProvider(
    name="NovoProvider",
    api_key_env="API_KEY",
    endpoint="https://...",
    make_headers=lambda k: {...},
    build_payload=lambda p, t: {...},
    parse_response=parse_json_text_response
))
```

---

### 11.2 Ajustar comportamento

* `usage_limit` → throughput
* `window_seconds` → rate limit
* `timeout` → latência tolerada

---

### 11.3 Melhorar seleção (opcional)

Substituir:

```python
primeiro disponível
```

Por:

```text
score operacional
```

Exemplos de sinais:

* latência
* taxa de erro
* cooldown residual

---

### 11.4 Validação leve de resposta

Sem semântica:

* tamanho mínimo
* presença de texto
* estrutura básica

---

## 12. Modelo mental correto

Isso NÃO é:

* orchestrator inteligente
* sistema semântico
* avaliador de resposta

---

Isso é:

```text
um sistema de execução resiliente guiado por falha
```

---

## 13. Forma mais condensada

```text
tenta executar
↓
observa falha
↓
altera estado
↓
tenta novamente
```

---

## 14. Quando usar

Use quando você quer:

* alta disponibilidade
* múltiplos providers
* simplicidade extrema
* zero dependência de vendor

---

## 15. Quando NÃO usar

Não use quando você precisa:

* ranking de qualidade
* roteamento por tipo de tarefa
* controle fino de output

---

## 16. Essência

> O sistema funciona porque transforma falha em informação e usa isso para navegar um espaço de execução instável até convergir em uma resposta.

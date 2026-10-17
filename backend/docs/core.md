# 0. Definição do sistema

> Engine de execução resiliente para múltiplos providers heterogêneos, com convergência em saída textual e seleção baseada exclusivamente em estado operacional.

---

# 1. Invariantes globais (isso define tudo)

### (1) Convergência de saída

```text
∀ execução → str
```

---

### (2) Independência de provider

Cada provider é:

```text
isolado + autossuficiente + stateful localmente
```

---

### (3) Roteamento não semântico

```text
decisão ≠ conteúdo
decisão = estado operacional
```

---

### (4) Fail-open

```text
erro → não interrompe
erro → deforma estado
```

---

### (5) Execução oportunista

```text
primeiro provider viável vence
```

---

# 2. Componentes

---

## 2.1 `AIProvider` — unidade fundamental

### Papel

Representa um backend executável com:

* contrato de entrada
* contrato de saída
* estado interno
* regras de disponibilidade

---

### Estrutura

```python
AIProvider:
    name
    api_key_env
    endpoint
    make_headers
    build_payload
    parse_response
```

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

### Interpretação

Isso é:

> **um ator com memória temporal e capacidade limitada**

---

### Métodos

#### `has_key()`

Valida existência de credencial.

---

#### `can_use()`

```text
Verifica se o provider pode ser utilizado neste instante.
```

Critérios:

1. janela atual válida?
2. não está em cooldown (`exhausted_until`)?
3. não excedeu limite?

---

#### `mark_usage()`

```text
Atualiza consumo e ativa cooldown se necessário.
```

---

#### `force_exhaust(ttl)`

```text
Remove provider do espaço de escolha temporariamente.
```

---

#### `send(prompt, temperature)`

```text
Executa chamada externa (HTTP ou equivalente).
```

Não garante sucesso.
Retorna resposta bruta.

---

## 2.2 `ProviderManager` — scheduler

### Papel

Gerenciar múltiplos providers e decidir:

```text
quem executa agora
```

---

### Estado

```python
providers[]
idx (round-robin)
lock
```

---

### Estratégia base

* round-robin
* skip dinâmico
* retry adaptativo

---

### Métodos

---

#### `_next_index()`

```text
Gera ponto inicial de busca com fairness.
```

---

#### `get_available_provider()`

```text
Busca o próximo provider utilizável.
```

Algoritmo:

1. define ponto inicial
2. percorre lista circular
3. retorna primeiro `can_use == True`

---

#### `ask(prompt)`

### Esse é o loop principal

---

## Fluxo interno completo:

```text
for tentativa em N:
    provider = get_available_provider()

    if nenhum:
        break

    try:
        resp = send()

        if sucesso HTTP:
            parse
            mark_usage
            return resposta

        elif 429:
            penalização média

        elif erro HTTP:
            penalização curta

    except:
        penalização mínima
```

---

### Interpretação

Isso é:

> **busca iterativa em espaço mutável com poda dinâmica**

---

# 3. Dinâmica temporal (o coração da engine)

---

## Estado global (implícito)

```text
S = união dos estados de todos providers
```

---

## A cada execução:

```text
S_t → tentativa → observação → mutação → S_{t+1}
```

---

## O sistema aprende implicitamente:

* quais providers estão saudáveis
* quais estão falhando
* quando evitar cada um

---

Sem armazenar histórico explícito.

---

# 4. Parser layer (`ai_parsers.py`)

---

## Papel

Garantir:

```text
Response heterogêneo → string
```

---

## Estratégia

### (1) Caminhos conhecidos

* padrões esperados (Google, OpenAI-like)

---

### (2) Fallback estrutural

```python
_find_text_in_json
```

Busca:

* recursiva
* limitada por profundidade
* baseada em chaves comuns

---

### Interpretação

> extração por invariantes fracos em estrutura desconhecida

---

### Consequência

* alta tolerância a mudanças de API
* baixa garantia semântica

---

# 5. Builders (`ai_builders.py`)

---

## Papel

Converter:

```text
(prompt, temperatura) → payload específico
```

---

## Natureza

São:

> funções de projeção para espaço de entrada do provider

---

## Observação importante

Existe dois tipos:

---

### Tipo A — declarativo

```text
retorna payload
```

---

### Tipo B — executável (OpenAI)

```text
executa e retorna string
```

---

### Implicação

O sistema aceita:

> múltiplos contratos internos, desde que saída final converja

---

# 6. Router (`ai_router.py`)

---

## Papel real

Não roteia semanticamente.

Ele:

* instancia providers
* injeta configurações
* conecta tudo

---

## Função

```text
bootstrap do sistema
```

---

# 7. Modelo operacional completo

---

## Pipeline lógico

```text
input
 ↓
ProviderManager.ask
 ↓
seleção (estado)
 ↓
execução (provider)
 ↓
parse (normalização)
 ↓
string
```

---

## Pipeline dinâmico

```text
tentativa
 ↓
falha
 ↓
mutação de estado
 ↓
nova tentativa
```

---

# 8. Modos de operação (implícitos)

---

## Modo 1 — single attempt

* baixa latência
* baixa garantia

---

## Modo 2 — multi attempt

* alta robustez
* maior custo/latência

---

## Observação

Isso é controlado implicitamente por:

```text
len(providers)
```

---

# 9. Tratamento de erro

---

## Filosofia

```text
erro não é exceção lógica
erro é estado operacional
```

---

## Transformações

| Evento    | Ação            |
| --------- | --------------- |
| 429       | cooldown médio  |
| erro HTTP | cooldown curto  |
| exception | cooldown mínimo |

---

## Resultado

Sistema nunca quebra por falha externa.

---

# 10. Propriedades emergentes

---

## (1) Auto-balanceamento

Providers saudáveis recebem mais carga.

---

## (2) Adaptação dinâmica

Sem algoritmo explícito de learning.

---

## (3) Robustez a instabilidade

APIs instáveis não derrubam sistema.

---

## (4) Escalabilidade linear

```text
custo ∝ número de providers
```

---

## (5) Independência de vendor

Nenhum provider é essencial.

---

# 11. Limites estruturais

---

## (1) Sem avaliação de qualidade

```text
qualquer output ≈ válido
```

---

## (2) Sem diferenciação por tarefa

```text
input não influencia escolha
```

---

## (3) Dependência de existência de provider funcional

Se todos falharem:

```text
RuntimeError
```

---

# 12. Essência do mecanismo

---

> O sistema funciona porque transforma heterogeneidade externa em homogeneidade interna, e resolve seleção como problema de estado físico ao invés de problema semântico.

---

# 13. Forma mais condensada possível

---

```text
Sistema que:
- tenta executar
- observa falha
- altera espaço de escolha
- tenta novamente
até convergir ou esgotar
```

---

Se você usar isso como núcleo, você consegue:

* documentar comportamento
* explicar trade-offs
* expor API corretamente
* evitar misuse do cliente

---

Se quiser, próximo passo eu posso converter isso direto em:
→ doc estilo README técnico utilizável
ou
→ comentários inline já prontos pros arquivos

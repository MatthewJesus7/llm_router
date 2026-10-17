# doc temporaria pra eu fazer depois


Questões com Grok e Claude
Grok (xAI) enfrenta "high demand" e rate limits na API devido a picos de uso e incidentes recentes (outages em março), mas suporta pesquisa em tempo real via "enable_search": true na API – não ausente, mas sobrecarregado pela hype.


"enable_search": true



Para usar o **motor de pesquisa da API do Grok** (web search / live search), você precisa “habilitar” o *tool* de busca (`web_search` ou `x_search`) na sua requisição, em vez de usar apenas o chat padrão sem pesquisa. [help.apiyi](https://help.apiyi.com/en/xai-grok-api-x-search-web-search-guide-en.html)

Vou te dar um tutorial prático em Python, já que você já está usando a API; basta adaptar o parâmetro `tools` para *ativar* o mecanismo de busca.

***

### 1. Como funciona o motor de pesquisa

O Grok expõe o recurso de busca via parâmetro `tools` (ou `search_parameters` em alguns endpoints). Basicamente:

- Sem `tools`: você só usa o modelo como um chat padrão, sem olhar a web em tempo real.  
- Com `tools`: você “liga” o `web_search` ou `x_search` e o Grok pode buscar informações na web (ou no X/Twitter) antes de responder. [docs.x](https://docs.x.ai/developers/tools/web-search)

***

### 2. Endpoint oficial e autorização

Você já deve estar usando algo como:

```bash
POST https://api.x.ai/v1/chat/completions
```

ou

```bash
POST https://api.x.ai/v1/responses
```

Cabeçalhos:

```http
Authorization: Bearer <seu_XAI_API_KEY>
Content-Type: application/json
```

`<seu_XAI_API_KEY>` é a mesma chave que você já usa hoje. [help.apiyi](https://help.apiyi.com/en/xai-grok-api-x-search-web-search-guide-en.html)

***

### 3. Ativar o motor de web search (web_search)

Supondo que você esteja usando `/chat/completions` ou `/responses`, o truque é colocar `tools` no JSON:

#### Exemplo em Python (via `requests`)

```python
import requests
import os

XAI_API_KEY = os.getenv("XAI_API_KEY")  # sua chave habituada

url = "https://api.x.ai/v1/responses"

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {XAI_API_KEY}",
}

payload = {
    "model": "grok-4.20-reasoning",  # ou outro modelo Grok disponível
    "input": [
        {
            "role": "user",
            "content": "Quais são as últimas notícias sobre xAI hoje?"
        }
    ],
    "tools": [
        {
            "type": "web_search",
            # Opcional: filtrar domínios
            # "filters": {
            #     "allowed_domains": ["x.ai", "news.com.br"]
            # }
        }
    ]
}

response = requests.post(url, headers=headers, json=payload)
print(response.json())
```

Neste exemplo, o Grok vai:

1. receber o texto do usuário;  
2. ver que há um `tool` do tipo `web_search`;  
3. realizar uma busca na web;  
4. retornar a resposta com a informação mais recente (e, configurando, até citações). [docs.x](https://docs.x.ai/developers/tools/web-search)

***

### 4. Usar apenas buscas no X (tweets / posts) com `x_search`

Se quiser pesquisar só no X (Twitter), use `x_search`:

```python
payload = {
    "model": "grok-4.20-reasoning",
    "input": [
        {"role": "user", "content": "O que Elon Musk falou sobre Grok hoje?"}
    ],
    "tools": [
        {
            "type": "x_search",
            # Opcional: limitar a certas contas
            "allowed_x_handles": ["elonmusk", "xaboratory"]
        }
    ]
}
```

O `x_search` olha posts da plataforma X; `web_search` é mais “web geral” (Google‑style). [help.apiyi](https://help.apiyi.com/en/xai-grok-api-x-search-web-search-guide-en.html)

***

### 5. Parâmetros de controle de busca (modo e citações)

Em alguns endpoints, você também pode usar `search_parameters` com `mode` e `return_citations`:

```python
payload = {
    "model": "grok-3-latest",  # exemplo antigo, mas ainda válido em alguns casos
    "messages": [
        {"role": "user", "content": "Resuma as notícias globais das últimas 24h."}
    ],
    "search_parameters": {
        "mode": "auto",          # ou "off" / "force" dependendo da API
        "return_citations": True # retorna URLs de onde tirou a info
    }
}
```

Não todos os endpoints aceitam `search_parameters`; o `tools` com `web_search` é o padrão mais recente. [community.n8n](https://community.n8n.io/t/how-to-use-grok-ai-with-live-search-feature/121903)

***

### 6. Como adaptar o que você já usa hoje

Se hoje você está chamando algo como:

```python
payload = {
    "model": "grok-3-latest",
    "messages": [...],
    # sem tools nem search_parameters
}
```

Basta acrescentar:

```python
payload["tools"] = [
    {"type": "web_search"}
]
```

ou, se quiser validar domínios:

```python
payload["tools"] = [
    {
        "type": "web_search",
        "filters": {"allowed_domains": ["site-confiavel.com.br"]}
    }
]
```

Depois envie o mesmo `POST` para o mesmo endpoint. [docs.x](https://docs.x.ai/developers/tools/web-search)

***

### 7. Avaliar o que você ganha com a pesquisa

Com o `web_search` ativado, você consegue:

- Informações **em tempo real** (notícias, preços, eventos, etc.);  
- Respostas baseadas em **fontes externas**, não só no conhecimento treinado estático;  
- Citações (`return_citations = True` ou via `tools`), se você quiser acompanhar de onde veio cada dado. [community.n8n](https://community.n8n.io/t/how-to-use-grok-ai-with-live-search-feature/121903)

Se quiser, você pode colar aqui um exemplo da sua chamada atual à API (sem expor a chave) e eu mostro o JSON exatamente ajustado para ligar o motor de pesquisa.
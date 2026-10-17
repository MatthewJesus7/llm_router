O repositório oficial é mantido pela organização **open-webui**.

### Repositório Oficial

* **GitHub:** `[https://github.com/open-webui/open-webui.git](https://github.com/open-webui/open-webui.git)`

---

#### Clonar o Código-Fonte (Para Dev / Customização)

Se você quer clonar a base de código para inspecionar, alterar ou fazer o build na mão:

```bash
# 1. Clonar o repositório
git clone https://github.com/open-webui/open-webui.git
cd open-webui

# 2. Copiar o arquivo de ambiente
cp -R .env.example .env

# 3. Rodar via Docker Compose
docker compose up -d --build

```

---

### Como Conectar no Seu Backend

Quando a interface subir (em `http://localhost:3000`):

1. Crie uma conta de administrador inicial na tela de login.
2. Vá em **Admin Panel** (Painel de Administração) -> **Settings** (Configurações) -> **Connections** (Conexões).
3. No campo **OpenAI API**, coloque o endereço do seu backend (ex: `http://localhost:8000/v1`).
4. Clique no ícone de atualização (*verify connection*). O Open WebUI fará um `GET /v1/models` no seu backend e todos os seus modelos cadastrados aparecerão imediatamente no dropdown superior do chat.



Como usar com essa alteração:

    Para subir tudo (incluindo o Ollama):
    Bash

    docker compose --profile optional up -d

    Para subir apenas o Open-WebUI (sem puxar nem iniciar o Ollama):
    Bash

    docker compose up -d





    Opção 2: Se preferir usar o nvm para alternar para uma versão suportada (Node 22)

Se você tiver o NVM (Node Version Manager) instalado, você pode rodar na mesma pasta:
Bash

nvm install 22
nvm use 22
npm install
npm run dev

Depois de rodar o npm install (com --force ou usando o Node 22), o ambiente de desenvolvimento subirá normalmente com:
Bash

npx vite dev --host
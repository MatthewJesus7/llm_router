O repositório oficial é mantido pela organização **open-webui**.

### Repositório Oficial

* **GitHub:** `[https://github.com/open-webui/open-webui.git](https://github.com/open-webui/open-webui.git)`

---

### Como Clonar e Rodar

#### Opção 1: Via Docker (Recomendado)

Se você quer apenas subir a aplicação sem compilar o código fonte localmente, use o container oficial. Para conectar com o seu backend local, passe a URL via variável de ambiente:

```bash
docker run -d -p 3000:8080 \
  -e OPENAI_API_BASE_URL="http://host.docker.internal:SUA_PORTA/v1" \
  -e OPENAI_API_KEY="sua_key_se_houver" \
  -v open-webui:/app/backend/data \
  --name open-webui \
  --restart always \
  ghcr.io/open-webui/open-webui:main

```

*(Nota: `host.docker.internal` permite que o container Docker acesse a porta do seu backend rodando no `localhost` da sua máquina).*

---

#### Opção 2: Clonar o Código-Fonte (Para Dev / Customização)

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
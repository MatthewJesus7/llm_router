```javascript
// model_manager.js
class OpenRouterModelManager {
    constructor(storageKey = 'custom_openrouter_models') {
        this.storageKey = storageKey;
        this._initDefault();
    }

    _initDefault() {
        if (!localStorage.getItem(this.storageKey)) {
            const defaults = [
                "google/gemma-2-9b-it:free",
                "meta-llama/llama-3.1-8b-instruct:free",
                "mistralai/mistral-7b-instruct:v0.3",
                "deepseek/deepseek-chat"
            ];
            this.saveModels(defaults);
        }
    }

    getModels() {
        const data = localStorage.getItem(this.storageKey);
        return data ? JSON.parse(data) : [];
    }

    saveModels(models) {
        localStorage.setItem(this.storageKey, JSON.stringify(models));
    }

    addModel(modelId) {
        const trimmed = modelId.trim();
        if (!trimmed) return this.getModels();
        const models = this.getModels();
        if (!models.includes(trimmed)) {
            models.push(trimmed);
            this.saveModels(models);
        }
        return models;
    }

    removeModel(modelId) {
        let models = this.getModels();
        models = models.filter(m => m !== modelId);
        this.saveModels(models);
        return models;
    }

    updateModel(oldId, newId) {
        const trimmed = newId.trim();
        if (!trimmed) return this.getModels();
        let models = this.getModels();
        const index = models.indexOf(oldId);
        if (index !== -1) {
            models[index] = trimmed;
            this.saveModels(models);
        }
        return models;
    }

    exportJSON() {
        const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(this.getModels(), null, 2));
        const anchor = document.createElement('a');
        anchor.setAttribute("href", dataStr);
        anchor.setAttribute("download", "openrouter_models.json");
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
    }

    importJSON(jsonString) {
        try {
            const parsed = JSON.parse(jsonString);
            if (Array.isArray(parsed)) {
                this.saveModels(parsed);
                return true;
            }
        } catch (e) {
            console.error("JSON inválido", e);
        }
        return false;
    }
}

```

```html
<!-- Exqueleto HTML para futura integração da interface de CRUD -->
<div id="model-manager-app">
    <div class="actions">
        <input type="text" id="new-model-input" placeholder="ex: provider/model-name">
        <button id="btn-add">Adicionar Modelo</button>
        <button id="btn-export">Exportar JSON</button>
        <input type="file" id="file-import" accept=".json" style="display:none">
        <button id="btn-import-trigger">Importar JSON</button>
    </div>
    
    <ul id="model-list">
        <!-- Renderizado dinamicamente via JS -->
    </ul>
</div>

<script>
const manager = new OpenRouterModelManager();

function renderUI() {
    const listEl = document.getElementById('model-list');
    const models = manager.getModels();
    listEl.innerHTML = '';

    models.forEach(model => {
        const li = document.createElement('li');
        li.innerHTML = `
            <span>${model}</span>
            <button onclick="editModel('${model}')">Editar</button>
            <button onclick="deleteModel('${model}')">Excluir</button>
        `;
        listEl.appendChild(li);
    });
}

document.getElementById('btn-add').addEventListener('click', () => {
    const input = document.getElementById('new-model-input');
    manager.addModel(input.value);
    input.value = '';
    renderUI();
});

function deleteModel(id) {
    manager.removeModel(id);
    renderUI();
}

function editModel(oldId) {
    const newId = prompt("Novo ID do modelo:", oldId);
    if (newId) {
        manager.updateModel(oldId, newId);
        renderUI();
    }
}

document.getElementById('btn-export').addEventListener('click', () => {
    manager.exportJSON();
});

document.getElementById('btn-import-trigger').addEventListener('click', () => {
    document.getElementById('file-import').click();
});

document.getElementById('file-import').addEventListener('change', (event) => {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
        if (manager.importJSON(e.target.result)) {
            renderUI();
            alert('Importado com sucesso!');
        } else {
            alert('Erro ao importar arquivo.');
        }
    };
    reader.readAsText(file);
});

// Inicialização
renderUI();
</script>

```
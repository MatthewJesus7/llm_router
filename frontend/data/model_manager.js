// model_manager.js
class OpenRouterModelManager {
    constructor(storageKey = 'custom_openrouter_models') {
        this.storageKey = storageKey;
        this._initDefault();
    }

    _initDefault() {
        if (!localStorage.getItem(this.storageKey)) {
            const defaults = [
                "google/gemma-2-9b-it",
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

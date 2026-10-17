<script>
    import { goto } from '$app/navigation';
    import { WEBUI_NAME, config } from '$lib/stores';
    import { onMount, getContext } from 'svelte';
    import { fade } from 'svelte/transition';

    const i18n = getContext('i18n');

    let loaded = false;

    onMount(async () => {
        if ($config) {
            await goto('/');
        }

        loaded = true;
    });
</script>

{#if loaded}
    <div 
        class="fixed bottom-6 right-6 z-50 max-w-sm w-full bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 shadow-2xl rounded-2xl p-5 text-gray-800 dark:text-gray-100 backdrop-blur-lg"
        in:fade={{ duration: 200 }}
    >
        <div class="flex flex-col gap-2">
            <div class="flex items-center justify-between">
                <h3 class="font-semibold text-base tracking-tight flex items-center gap-2">
                    <span class="inline-block w-2.5 h-2.5 rounded-full bg-amber-500 animate-pulse"></span>
                    Modo Frontend Isolado
                </h3>
            </div>

            <p class="text-xs text-gray-600 dark:text-gray-400 leading-relaxed">
                O backend padrão não foi detectado. Sua interface está rodando de forma independente e pronta para conectar ao seu roteador multiagente.
            </p>

            <div class="mt-3 flex items-center justify-end gap-2 pt-2 border-t border-gray-100 dark:border-gray-800">
                <button
                    class="px-4 py-1.5 rounded-xl bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 transition text-xs font-medium"
                    on:click={() => {
                        location.href = '/';
                    }}
                >
                    Reconectar
                </button>
            </div>
        </div>
    </div>
{/if}
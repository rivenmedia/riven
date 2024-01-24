<script lang=ts>
    import { Check, X } from 'lucide-svelte';
    import { formatWords } from '$lib/helpers';
    export let statusData: Record<string, boolean> = {};
</script>

<div class="flex flex-col gap-2 items-start mt-2">
    {#each Object.keys(statusData) as serviceStatus}
        <div class="flex gap-1 items-center">
            {#if statusData[serviceStatus]}
                <div class="p-1 bg-green-500 rounded-full">
                    <Check class="w-4 h-4 text-white" />
                </div>
                <p class="text-muted-foreground">
                    <span class="font-semibold">{formatWords(serviceStatus)}</span> is configured
                </p>
            {:else}
                <div class="p-1 bg-red-500 rounded-full">
                    <X class="w-4 h-4 text-white" />
                </div>
                <p class="text-muted-foreground">
                    <span class="font-semibold">{formatWords(serviceStatus)}</span> is not configured
                </p>
            {/if}
        </div>
    {/each}
</div>
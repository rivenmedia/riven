<script lang="ts">
	import { Sun, Moon } from 'lucide-svelte';
	import { Button } from '$lib/components/ui/button';
	import { setMode, mode } from 'mode-watcher';
</script>

{#if $mode === 'light'}
	<Button
        size="sm"
		on:click={() => {
			setMode('dark');
		}}
		class="max-w-max"
	>
		<Moon class="h-4 w-4" />
	</Button>
{:else}
	<Button
        size="sm"
		on:click={() => {
			setMode('light');
		}}
		class="max-w-max"
	>
		<Sun class="h-4 w-4" />
	</Button>
{/if}

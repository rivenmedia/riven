<script lang="ts">
	import { Sun, Moon } from 'lucide-svelte';
	import { Button } from '$lib/components/ui/button';
	import { setMode, mode } from 'mode-watcher';
	import * as Tooltip from '$lib/components/ui/tooltip';
</script>

{#if $mode === 'light'}
	<Tooltip.Root>
		<Tooltip.Trigger asChild let:builder>
			<Button
				builders={[builder]}
				size="sm"
				on:click={() => {
					setMode('dark');
				}}
				class="max-w-max"
			>
				<Moon class="h-4 w-4" />
			</Button>
		</Tooltip.Trigger>
		<Tooltip.Content>
			<p>Dark mode</p>
		</Tooltip.Content>
	</Tooltip.Root>
{:else}
	<Tooltip.Root>
		<Tooltip.Trigger asChild let:builder>
			<Button
				builders={[builder]}
				size="sm"
				on:click={() => {
					setMode('light');
				}}
				class="max-w-max"
			>
				<Sun class="h-4 w-4" />
			</Button>
		</Tooltip.Trigger>
		<Tooltip.Content>
			<p>Light mode</p>
		</Tooltip.Content>
	</Tooltip.Root>
{/if}

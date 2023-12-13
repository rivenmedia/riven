<script lang="ts">
	import { convertPlexDebridItemsToObject } from '$lib/helpers.js';
	import { invalidateAll } from '$app/navigation';
	import { Button } from '$lib/components/ui/button';
	import * as Tooltip from '$lib/components/ui/tooltip';
	import { Loader2, ArrowUpRight, RotateCw } from 'lucide-svelte';
	import StatusMediaCard from '$lib/components/status-media-card.svelte';

	export let data;

	let reloadButtonLoading = false;

	async function reloadData() {
		reloadButtonLoading = true;
		await invalidateAll();
		reloadButtonLoading = false;
	}
</script>

<svelte:head>
	<title>Iceberg | Status</title>
</svelte:head>

<div class="flex flex-col gap-4 p-8 md:px-24 lg:px-32">
	{#await data.streamed.items}
		<div class="flex items-center gap-1 w-full justify-center">
			<Loader2 class="animate-spin w-4 h-4" />
			<p class="text-lg text-muted-foreground">Loading library items...</p>
		</div>
	{:then items}
		<div class="flex flex-row items-center justify-between">
			<div class="flex flex-col items-start">
				<h1 class="text-4xl font-semibold">Status</h1>
				<p class="text-lg text-muted-foreground">
					This page shows the status of your library items.
				</p>
			</div>
			<div class="flex flex-row items-center gap-2">
				<Tooltip.Root>
					<Tooltip.Trigger asChild let:builder>
						<Button
							builders={[builder]}
							disabled={reloadButtonLoading}
							type="button"
							size="sm"
							class="max-w-max"
							on:click={reloadData}
						>
							<RotateCw class="h-4 w-4" />
						</Button>
					</Tooltip.Trigger>
					<Tooltip.Content>
						<p>Reload data</p>
					</Tooltip.Content>
				</Tooltip.Root>

				<Tooltip.Root>
					<Tooltip.Trigger asChild let:builder>
						<Button
							builders={[builder]}
							size="sm"
							class="max-w-max"
							href="https://app.plex.tv/desktop"
						>
							<ArrowUpRight class="h-4 w-4" />
						</Button>
					</Tooltip.Trigger>
					<Tooltip.Content>
						<p>Open Plex</p>
					</Tooltip.Content>
				</Tooltip.Root>
			</div>
		</div>
		{@const plexDebridItems = convertPlexDebridItemsToObject(items.items)}
		{#each Object.keys(plexDebridItems) as key (key)}
			<div class="flex flex-col gap-4">
				{#each plexDebridItems[key] as item}
					<StatusMediaCard plexDebridItem={item} />
				{/each}
			</div>
		{/each}
	{:catch error}
		<p>{error.message}</p>
	{/await}
</div>

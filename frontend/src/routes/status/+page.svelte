<script lang="ts">
	import { formatState, convertPlexDebridItemsToObject } from '$lib/helpers.js';
	import { invalidateAll } from '$app/navigation';
	import { Button } from '$lib/components/ui/button';
	import { Loader2, ArrowUpRight, RotateCw } from 'lucide-svelte';
	import StatusMediaCard from '$lib/components/status-media-card.svelte';
	export let data;
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
				<Button
					type="button"
					size="sm"
					class="max-w-max"
					on:click={() => {
						invalidateAll();
					}}
				>
					<RotateCw class="h-4 w-4" />
				</Button>
				<Button type="button" size="sm" class="max-w-max" href="https://app.plex.tv/desktop">
					<ArrowUpRight class="h-4 w-4" />
				</Button>
			</div>
		</div>
		{@const plexDebridItems = convertPlexDebridItemsToObject(items.items)}
		{#each Object.keys(plexDebridItems) as key (key)}
			<h2 class="text-2xl font-semibold">{formatState(key)}</h2>
			<div class="flex flex-row flex-wrap w-full gap-4">
				{#each plexDebridItems[key] as item}
					<StatusMediaCard plexDebridItem={item} />
				{/each}
			</div>
		{/each}
	{:catch error}
		<p>{error.message}</p>
	{/await}
</div>

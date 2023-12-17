<script lang="ts">
	import { convertPlexDebridItemsToObject, formatWords } from '$lib/helpers';
	import { invalidateAll } from '$app/navigation';
	import { Button } from '$lib/components/ui/button';
	import * as Tooltip from '$lib/components/ui/tooltip';
	import * as Accordion from '$lib/components/ui/accordion';
	import { Loader2, ArrowUpRight, RotateCw, Info } from 'lucide-svelte';
	import StatusMediaCard from '$lib/components/status-media-card.svelte';
	import { toast } from 'svelte-sonner';
	import type { StatusInfo } from '$lib/types';
	import { onMount } from 'svelte';

	export let data;

	let reloadButtonLoading = false;

	async function reloadData(message: string = 'Refreshed data') {
		reloadButtonLoading = true;
		await invalidateAll();
		reloadButtonLoading = false;
		toast.success(message);
	}

	const statusInfo: StatusInfo = {
		UNKNOWN: {
			color: 'text-red-500',
			bg: 'bg-red-500',
			description: 'Unknown status'
		},
		CONTENT: {
			text: 'Requested',
			color: 'text-purple-500',
			bg: 'bg-purple-500',
			description: 'Item is requested from external service'
		},
		SCRAPE: {
			color: 'text-yellow-500',
			bg: 'bg-yellow-500',
			description: 'Item is scraped and will be downloaded'
		},
		DOWNLOAD: {
			color: 'text-yellow-500',
			bg: 'bg-yellow-500',
			description: 'Item is currently downloading'
		},
		SYMLINK: {
			color: 'text-yellow-500',
			bg: 'bg-yellow-500',
			description: 'Item is currently being symmlinked'
		},
		LIBRARY: {
			text: 'In Library',
			color: 'text-green-400',
			bg: 'bg-green-400',
			description: 'Item is in your library'
		},
		LIBRARY_PARTIAL: {
			color: 'text-blue-400',
			bg: 'bg-blue-400',
			description: 'Item is in your library and is ongoing'
		}
	};

	// every 5s reload data
	onMount(async () => {
		setInterval(async () => {
			await reloadData('Automatically refreshed data');
		}, 60000);
	});
</script>

<svelte:head>
	<title>Iceberg | Status</title>
</svelte:head>

<div class="flex flex-col gap-2 p-8 md:px-24 lg:px-32">
	{#await data.items}
		<div class="flex items-center gap-1 w-full justify-center">
			<Loader2 class="animate-spin w-4 h-4" />
			<p class="text-lg text-muted-foreground">Loading library items...</p>
		</div>
	{:then items}
		<div class="flex flex-row items-center justify-between">
			<div class="flex flex-col items-start">
				<h1 class="text-3xl md:text-4xl font-semibold">
					Status <span class="text-xl md:text-2xl">({items.items.length})</span>
				</h1>
				<p class="md:text-lg text-muted-foreground">
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
							variant="outline"
							size="sm"
							class="max-w-max"
							on:click={async () => {
								await reloadData();
							}}
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
							variant="outline"
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

		<Accordion.Root>
			<Accordion.Item value="item-1">
				<Accordion.Trigger>
					<div class="flex items-center gap-2 md:text-lg">
						<Info class="h-4 w-4" />
						<p>Learn more about status badges</p>
					</div>
				</Accordion.Trigger>
				<Accordion.Content>
					<ul class="list-disc list-inside md:text-lg">
						{#each Object.keys(statusInfo) as key (key)}
							<li>
								<span class="font-semibold {statusInfo[key].color}">
									{statusInfo[key].text ?? formatWords(key)}
								</span>
								{statusInfo[key].description}
							</li>
						{/each}
					</ul>
				</Accordion.Content>
			</Accordion.Item>
		</Accordion.Root>
		{@const plexDebridItems = convertPlexDebridItemsToObject(items.items)}
		{#each Object.keys(plexDebridItems) as key (key)}
			<div class="flex flex-col gap-4">
				{#each plexDebridItems[key] as item}
					<StatusMediaCard plexDebridItem={item} itemState={statusInfo[item.state]} />
				{/each}
			</div>
		{/each}
	{:catch error}
		<div class="flex flex-col items-center justify-center w-full h-full font-primary">
			<h1 class="text-4xl font-bold text-center">Something went wrong</h1>
			<p class="text-lg text-muted-foreground">Error message: {error.message}</p>
		</div>
	{/await}
</div>

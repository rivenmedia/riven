<script lang="ts">
	import type { PageData } from './$types';
	import { convertPlexDebridItemsToObject, formatWords } from '$lib/helpers';
	import { goto, invalidate } from '$app/navigation';
	import { Button } from '$lib/components/ui/button';
	import * as Tooltip from '$lib/components/ui/tooltip';
	import { Loader2, ArrowUpRight, RotateCw, Info } from 'lucide-svelte';
	import { toast } from 'svelte-sonner';
	import type { StatusInfo } from '$lib/types';
	import * as Carousel from '$lib/components/ui/carousel/index.js';

	export let data: PageData;

	let reloadButtonLoading = false;

	async function reloadData(message: string = 'Refreshed data') {
		reloadButtonLoading = true;
		await invalidate('api:states');
		reloadButtonLoading = false;
		toast.success(message);
	}

	const statusInfo: StatusInfo = {
		Unknown: {
			color: 'text-red-500',
			bg: 'bg-red-500',
			description: 'Unknown status'
		},
		Content: {
			text: 'Requested',
			color: 'text-purple-500',
			bg: 'bg-purple-500',
			description: 'Item is requested from external service'
		},
		Scrape: {
			color: 'text-yellow-500',
			bg: 'bg-yellow-500',
			description: 'Item is scraped and will be downloaded'
		},
		Download: {
			color: 'text-yellow-500',
			bg: 'bg-yellow-500',
			description: 'Item is currently downloading'
		},
		Symlink: {
			color: 'text-yellow-500',
			bg: 'bg-yellow-500',
			description: 'Item is currently being symmlinked'
		},
		Library: {
			text: 'In Library',
			color: 'text-green-400',
			bg: 'bg-green-400',
			description: 'Item is in your library'
		},
		LibraryPartial: {
			text: 'In Library (Partial)',
			color: 'text-blue-400',
			bg: 'bg-blue-400',
			description: 'Item is in your library and is ongoing'
		}
	};
</script>

<svelte:head>
	<title>Iceberg | Status</title>
</svelte:head>

<div class="flex flex-col gap-2 p-8 md:px-24 lg:px-32 w-full">
	{#await data.items}
		<div class="flex items-center gap-1 w-full justify-center">
			<Loader2 class="animate-spin w-4 h-4" />
			<p class="text-muted-foreground">Loading library items...</p>
		</div>
	{:then items}
		<div class="flex flex-row items-center justify-between w-full">
			<div class="flex flex-col items-start">
				<h1 class="text-2xl md:text-3xl font-semibold">
					Status <span class="text-lg md:text-xl">({items.items.length})</span>
				</h1>
				<p class="text-muted-foreground">This page shows the status of your library items.</p>
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

		{@const plexDebridItems = convertPlexDebridItemsToObject(items.items)}
		<div class="flex flex-col gap-12 mt-4 w-full">
			{#each Object.keys(plexDebridItems) as key (key)}
				<Carousel.Root
					opts={{
						align: 'start',
						dragFree: true
					}}
					class="flex flex-col gap-2 w-full"
				>
					<div class="flex items-center justify-between">
						<h3 class="text-xl md:text-2xl font-semibold">{formatWords(key)}</h3>
						<div class="flex items-center justify-center gap-2">
							<Carousel.Previous class="rounded-md static h-8 w-8" />
							<Carousel.Next class="rounded-md static h-8 w-8" />
						</div>
					</div>
					<Carousel.Content class="flex items-center gap-4">
						{#each plexDebridItems[key] as icebergItem}
							<Carousel.Item
								on:click={() => {
									console.log(icebergItem);
									goto(`/status/${icebergItem.imdb_id}`);
								}}
								style="background-image: url(https://images.metahub.space/poster/small/{icebergItem.imdb_id}/img);"
								class="bg-cover bg-center min-w-36 w-36 md:w-48 md:min-w-48 h-72 border max-w-max cursor-pointer"
							>
								...
							</Carousel.Item>
						{/each}
					</Carousel.Content>
				</Carousel.Root>
			{/each}
		</div>
	{:catch error}
		<div class="flex flex-col items-center justify-center w-full h-full font-primary">
			<h1 class="text-3xl font-bold text-center">Something went wrong</h1>
			<p class="text-base text-muted-foreground">Error message: {error.message}</p>
		</div>
	{/await}
</div>

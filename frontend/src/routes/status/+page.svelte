<script lang="ts">
	import type { PageData } from './$types';
	import { convertIcebergItemsToObject, formatDate, formatWords } from '$lib/helpers';
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
			description: 'Unknown status'
		},
		Content: {
			text: 'Requested',
			description: 'Items which are requested from content providers'
		},
		Scrape: {
			description: 'Items which are scraped from content providers and will be downloaded soon'
		},
		Download: {
			description: 'Items which are currently downloading'
		},
		Symlink: {
			description: 'Items which are undergoing symlink'
		},
		Library: {
			text: 'In Library',
			description: 'Items which are in your plex library'
		},
		LibraryPartial: {
			text: 'In Library (Partial)',
			description: 'Items which are in your plex library but are missing some files'
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

		{@const icebergItems = convertIcebergItemsToObject(items.items)}
		<div class="flex flex-col gap-12 mt-4 w-full">
			{#each Object.keys(icebergItems) as key (key)}
				<Carousel.Root opts={{ dragFree: true }} class="w-full max-w-full flex flex-col gap-4">
					<div class="flex items-center justify-between">
						<div class="flex flex-col">
							<h3 class="text-xl md:text-2xl font-semibold">
								{statusInfo[key].text ?? formatWords(key)}
							</h3>
							<p class="text-muted-foreground text-sm">{statusInfo[key].description}</p>
						</div>
						<div class="flex items-center justify-center gap-2 mt-6">
							<Carousel.Previous class="rounded-md static h-8 w-8" />
							<Carousel.Next class="rounded-md static h-8 w-8" />
						</div>
					</div>
					<Carousel.Content class="flex flex-row h-full w-full">
						{#each icebergItems[key] as item}
							<Carousel.Item class="flex-none mr-2 min-w-0 max-w-max w-full h-full group/item">
								<div class="flex flex-col w-full h-full max-w-[144px] md:max-w-[176px]">
									<img
										alt={item.imdb_id}
										class="bg-cover bg-center h-[216px] w-[144px] md:w-[176px] md:h-[264px] rounded-md border-muted group-hover/item:scale-105 duration-300 transition-all ease-in-out"
										src={`https://images.metahub.space/poster/small/${item.imdb_id}/img`}
									/>
									<a
										href="/status/item/{item.item_id}"
										class="text-start text-sm mt-2 text-ellipsis line-clamp-1 group-hover/item:underline focus:underline"
										>{item.title}</a
									>
									<p class="text-muted-foreground text-xs mt-1">
										{formatDate(item.aired_at, 'year')}
									</p>
								</div>
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

<script lang="ts">
	import type { PageData } from './$types';
	import { convertIcebergItemsToObject, formatDate, formatWords } from '$lib/helpers';
	import { goto, invalidate } from '$app/navigation';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import * as Tooltip from '$lib/components/ui/tooltip';
	import * as Dialog from '$lib/components/ui/dialog';
	import { Loader2, ArrowUpRight, RotateCw, MoveUpRight, Info, Trash } from 'lucide-svelte';
	import { toast } from 'svelte-sonner';
	import type { StatusInfo } from '$lib/types';
	import * as Carousel from '$lib/components/ui/carousel/index.js';
	import { Skeleton } from '$lib/components/ui/skeleton';

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

	let extendedDataLoading = false;
	let extendedItem: any;

	async function getExtendedData(id: number) {
		extendedDataLoading = true;
		// sleep for 500ms to prevent flickering
		// await new Promise((resolve) => setTimeout(resolve, 50000));
		const res = await fetch(`/api/items/${id}`);
		const data = await res.json();
		extendedItem = data.item;
		extendedDataLoading = false;
	}
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
			{#if Object.keys(icebergItems).length === 0}
				<div class="flex flex-col w-full h-full font-primary">
					<h3 class="text-xl font-semibold">No items found :(</h3>
					<p class="text-sm text-muted-foreground">
						You can request items from the content services configured.
					</p>
				</div>
			{:else}
				{#each Object.keys(icebergItems) as key (key)}
					<Carousel.Root opts={{ dragFree: true }} class="w-full max-w-full flex flex-col gap-4">
						<div class="flex items-center justify-between">
							<div class="flex flex-col">
								<a href="/status/type/{key}" class="flex gap-1 items-center hover:underline">
									<h3 class="text-xl md:text-2xl font-semibold">
										{statusInfo[key]?.text ?? formatWords(key)}
									</h3>
									<MoveUpRight class="size-4 md:size-6" />
								</a>
								{#if statusInfo[key]}
									<p class="text-muted-foreground text-sm">{statusInfo[key].description}</p>
								{/if}
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
										<div class="relative h-full w-full">
											<img
												alt={item.imdb_id}
												loading="lazy"
												src={`https://images.metahub.space/poster/small/${item.imdb_id}/img`}
												class="bg-cover bg-center h-[216px] w-[144px] md:w-[176px] md:h-[264px] rounded-md border-muted group-hover/item:scale-105 duration-300 transition-all ease-in-out"
											/>
											<div class="absolute top-2 left-2">
												<Badge class="rounded-md bg-opacity-40 backdrop-blur-lg drop-shadow-lg">
													{item.type === 'movie' ? 'Movie' : 'TV Show'}
												</Badge>
											</div>
										</div>

										<Dialog.Root
											onOpenChange={async (open) => {
												if (open) {
													await getExtendedData(item.item_id);
												} else {
													extendedItem = null;
												}
											}}
										>
											<Dialog.Trigger>
												<p
													class="text-start text-sm mt-2 text-ellipsis line-clamp-1 group-hover/item:underline focus:underline"
												>
													{item.title}
												</p>
											</Dialog.Trigger>
											<Dialog.Content class="min-h-72 flex flex-col items-start justify-between">
												{#if extendedDataLoading || !extendedItem}
													<Dialog.Header class="w-full h-full">
														<Dialog.Title>{item.title}</Dialog.Title>
														<Dialog.Description class="w-full h-full">
															<Skeleton class="w-full h-32 mt-1" />
														</Dialog.Description>
													</Dialog.Header>
													<div class="flex flex-wrap items-center justify-start gap-2 mt-2">
														<Button disabled={true} variant="outline">
															<Info class="h-4 w-4 mr-2" />
															Details
														</Button>
														<Button disabled={true} variant="destructive">
															<Trash class="h-4 w-4 mr-2" />
															Delete
														</Button>
													</div>
												{:else}
													<Dialog.Header>
														<Dialog.Title>{item.title}</Dialog.Title>
														<Dialog.Description class="flex flex-col gap-1">
															{#if item.type != 'movie'}
																<p class="text-muted-foreground text-sm">
																	{extendedItem.seasons.length} seasons
																</p>
															{/if}
															<p class="text-muted-foreground text-sm">
																Aired {formatDate(item.aired_at, 'short')}
															</p>
															<div
																class="flex flex-wrap gap-2 w-full items-center justify-center md:justify-start"
															>
																{#each item.genres as genre}
																	<Badge variant="secondary">
																		{formatWords(genre)}
																	</Badge>
																{/each}
															</div>
														</Dialog.Description>
													</Dialog.Header>
													<div class="flex flex-col items-start">
														<p>
															The item was requested <span class="font-semibold"
																>{formatDate(item.requested_at, 'long', true)}</span
															>
															by <span class="font-semibold">{item.requested_by}</span>.
														</p>
														{#if item.scraped_at && item.scraped_at !== '1970-01-01T00:00:00'}
															<p>
																Last scraped <span class="font-semibold"
																	>{formatDate(item.scraped_at, 'long', true)}</span
																>
																for a total of
																<span class="font-semibold">{item.scraped_times}</span>
																times.
															</p>
														{:else}
															<p>Has not been scraped yet.</p>
														{/if}
													</div>
													<div class="flex flex-wrap items-start gap-2">
														<Button
															variant="outline"
															class="mt-2 flex items-center"
															href="/status/item/{item.item_id}"
														>
															<Info class="h-4 w-4 mr-2" />
															Details
														</Button>
														<Button
															disabled={true}
															variant="destructive"
															class="mt-2 flex items-center"
														>
															<Trash class="h-4 w-4 mr-2" />
															Delete
														</Button>
													</div>
												{/if}
											</Dialog.Content>
										</Dialog.Root>
										<p class="text-muted-foreground text-xs mt-1">
											{formatDate(item.aired_at, 'year')}
										</p>
										<p class="text-muted-foreground text-xs mt-1">
											{formatDate(item.requested_at, 'long', true)}
										</p>
									</div>
								</Carousel.Item>
							{/each}
						</Carousel.Content>
					</Carousel.Root>
				{/each}
			{/if}
		</div>
	{:catch error}
		<div class="flex flex-col items-center justify-center w-full h-full font-primary">
			<h1 class="text-3xl font-bold text-center">Something went wrong</h1>
			<p class="text-base text-muted-foreground">Error message: {error.message}</p>
		</div>
	{/await}
</div>

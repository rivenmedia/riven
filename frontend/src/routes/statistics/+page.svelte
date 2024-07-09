<script lang="ts">
	import type { PageData } from './$types';
	import Header from '$lib/components/header.svelte';
	import * as Card from '$lib/components/ui/card';
	import { clsx } from 'clsx';

	export let data: PageData;

	const statsData: { title: string; value: number }[] = [
		{
			title: 'Total Items',
			value: data.stats.data.total_items
		},
		{
			title: 'Total Movies',
			value: data.stats.data.total_movies
		},
		{
			title: 'Total Shows',
			value: data.stats.data.total_shows
		},
		{
			title: 'Incomplete Items',
			value: data.stats.data.incomplete_items
		}
	];

	const statesName: Record<string, string> = {
		Unknown: 'Unknown',
		Requested: 'Requested',
		Indexed: 'Indexed',
		Scraped: 'Scraped',
		Downloaded: 'Downloaded',
		Symlinked: 'Symlinked',
		Completed: 'Completed',
		PartiallyCompleted: 'Incomplete',
		Failed: 'Failed'
	};

	// https://images.metahub.space/poster/small/tt3083016/img
	const baseUrl = 'https://images.metahub.space/poster/small/';

	const convertTo: Record<string, string> = {
		Movie: 'movie',
		Show: 'tv'
	};
</script>

<Header />

<div class="flex w-full flex-col p-8 md:px-24 lg:px-32">
	<h2 class="text-xl md:text-2xl">Statistics</h2>
	<div class="mt-4 grid w-full grid-cols-2 gap-6 md:grid-cols-3 lg:grid-cols-4">
		{#each statsData as stat}
			<Card.Root>
				<Card.Header>
					<Card.Title class="text-sm font-medium lg:text-base">{stat.title}</Card.Title>
				</Card.Header>
				<Card.Content>
					{#if stat.title === 'Total Shows'}
						<p class="text-lg lg:text-3xl">{stat.value}</p>
						<p class="text-muted-foreground text-sm lg:text-base">
							{data.stats.data.total_seasons} Seasons
						</p>
						<p class="text-muted-foreground text-sm lg:text-base">
							{data.stats.data.total_episodes} Episodes
						</p>
					{:else}
						<p class="text-lg lg:text-3xl">{stat.value}</p>
					{/if}
				</Card.Content>
			</Card.Root>
		{/each}
	</div>

	<h2 class="mt-8 text-xl md:text-2xl">States</h2>
	<p class="text-muted-foreground text-sm lg:text-base">
		Tells the current state of the items in the library
	</p>
	<div class="mt-4 grid w-full grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-5">
		{#each Object.keys(data.stats.data.states) as state}
			<Card.Root
				class={clsx({
					'col-span-2': state === 'Completed'
				})}
			>
				<Card.Header>
					<Card.Title class="text-sm font-medium lg:text-base">{statesName[state]}</Card.Title>
				</Card.Header>
				<Card.Content>
					<p class="text-lg lg:text-3xl">{data.stats.data.states[state]}</p>
				</Card.Content>
			</Card.Root>
		{/each}
	</div>

	<div class="mt-8 flex w-full flex-col">
		<h2 class="text-xl md:text-2xl">Incomplete Items</h2>
		<p class="text-muted-foreground text-sm lg:text-base">Items that are not yet completed</p>
		<div class="no-scrollbar flex flex-wrap overflow-x-auto px-1 lg:p-0 mt-4">
			{#each data.incompleteItems.incomplete_items as item, i}
				<a
					href="/{convertTo[item.type]}/{item.imdb_id}"
					class="group relative mb-2 flex w-1/2 flex-shrink-0 flex-col gap-2 rounded-lg p-2 sm:w-1/4 lg:w-1/6 xl:p-[.4rem]"
				>
					<div class="relative aspect-[1/1.5] w-full overflow-hidden rounded-lg">
						<img
							src="{baseUrl}{item.imdb_id}/img"
							alt={item.title}
							class="h-full w-full object-cover object-center transition-all duration-300 ease-in-out group-hover:scale-105"
						/>
						<!-- <div
							class="absolute right-0 top-1 flex items-center justify-center gap-1 rounded-l-md bg-slate-900/70 px-[5px] py-1"
						>
							<Star class="size-3 text-yellow-400" />
							<span class="text-xs font-light text-white">
								{roundOff(item.vote_average)}
							</span>
						</div> -->
					</div>
				</a>
			{/each}
		</div>
	</div>
</div>

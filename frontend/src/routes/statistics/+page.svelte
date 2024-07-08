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
</script>

<Header />

<div class="flex w-full flex-col p-8 md:px-24 lg:px-32">
	<div class="grid w-full grid-cols-2 gap-6 md:grid-cols-3 lg:grid-cols-4">
		{#each statsData as stat}
			<Card.Root>
				<Card.Header>
					<Card.Title class="text-sm lg:text-base">{stat.title}</Card.Title>
				</Card.Header>
				<Card.Content>
					{#if stat.title === 'Total Shows'}
						<p class="text-lg lg:text-3xl">{stat.value}</p>
						<p class="text-muted-foreground text-sm lg:text-base">
							Seasons {data.stats.data.total_seasons}
						</p>
						<p class="text-muted-foreground text-sm lg:text-base">
							Episodes {data.stats.data.total_episodes}
						</p>
					{:else}
						<p class="text-lg lg:text-3xl">{stat.value}</p>
					{/if}
				</Card.Content>
			</Card.Root>
		{/each}
	</div>

	<div class="mt-4 grid w-full grid-cols-2 md:grid-cols-3 gap-4 lg:grid-cols-5">
		{#each Object.keys(data.stats.data.states) as state}
			<Card.Root
				class={clsx({
					'col-span-2': state === 'Completed',
				})}
			>
				<Card.Header>
					<Card.Title class="text-sm lg:text-base">{statesName[state]}</Card.Title>
				</Card.Header>
				<Card.Content>
					<p class="text-lg lg:text-3xl">{data.stats.data.states[state]}</p>
				</Card.Content>
			</Card.Root>
		{/each}
	</div>
</div>

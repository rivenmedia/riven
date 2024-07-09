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

	const servicesObject: Record<string, string> = {
		symlinklibrary: 'Symlink Library',
		traktindexer: 'Trakt Indexer',
		overseerr: 'Overseerr',
		plex_watchlist: 'Plex Watchlist',
		listrr: 'Listrr',
		mdblist: 'MDB List',
		trakt: 'Trakt',
		scraping: 'Scraping',
		annatar: 'Annatar',
		torrentio: 'Torrentio',
		knightcrawler: 'Knightcrawler',
		orionoid: 'Orionoid',
		jackett: 'Jackett',
		torbox: 'Torbox',
		mediafusion: 'Media Fusion',
		Prowlarr: 'Prowlarr',
		zilean: 'Zilean',
		symlink: 'Symlink',
		updater: 'Updater',
		plexupdater: 'Plex Updater',
		localupdater: 'Local Updater',
		realdebrid: 'Real Debrid',
		torbox_downloader: 'Torbox Downloader'
	};

	const coreServices = ['symlinklibrary', 'symlink', 'scraping', 'updater'];
	const downloaderServices = ['realdebrid', 'torbox', 'torbox_downloader'];
	const contentServices = ['mdblist', 'overseerr', 'plex_watchlist', 'listrr', 'trakt'];
	const scrapingServices = [
		'torrentio',
		'knightcrawler',
		'annatar',
		'jackett',
		'orionoid',
		'mediafusion',
		'torbox',
		'prowlarr',
		'zilean'
	];

	function sortServices(services: string[], data: Record<string, boolean>) {
		let sortedData = {} as Record<string, boolean>;

		for (let service of services) {
			sortedData[service] = data[service];
			if (!data[service]) {
				data[service] = false;
			}
		}
		return sortedData as Record<string, boolean>;
	}

	const coreServicesData = sortServices(coreServices, data.services.data);
	const downloaderServicesData = sortServices(downloaderServices, data.services.data);
	const contentServicesData = sortServices(contentServices, data.services.data);
	const scrapingServicesData = sortServices(scrapingServices, data.services.data);

	const coreServicesStatus = Object.keys(coreServicesData).map((service) => {
		return {
			name: servicesObject[service],
			status: coreServicesData[service]
		};
	});

	const downloaderServicesStatus = Object.keys(downloaderServicesData).map((service) => {
		return {
			name: servicesObject[service],
			status: downloaderServicesData[service]
		};
	});

	const contentServicesStatus = Object.keys(contentServicesData).map((service) => {
		return {
			name: servicesObject[service],
			status: contentServicesData[service]
		};
	});

	const scrapingServicesStatus = Object.keys(scrapingServicesData).map((service) => {
		return {
			name: servicesObject[service],
			status: scrapingServicesData[service]
		};
	});

	type ServiceStatus = {
		name: string;
		services: any;
	};

	const servicesStatus: ServiceStatus[] = [
		{
			name: 'Core services',
			services: coreServicesStatus
		},
		{
			name: 'Downloader services',
			services: downloaderServicesStatus
		},
		{
			name: 'Content services',
			services: contentServicesStatus
		},
		{
			name: 'Scraping services',
			services: scrapingServicesStatus
		}
	];

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
	<p class="text-muted-foreground text-sm lg:text-base">Statistics of the library</p>
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

	<h2 class="mt-8 text-xl md:text-2xl">Services</h2>
	<p class="text-muted-foreground text-sm lg:text-base">Tells the current status of the services</p>
	<div class="mt-4 grid w-full grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">
		{#each servicesStatus as service}
			<Card.Root>
				<Card.Header>
					<Card.Title class="text-sm font-medium lg:text-base">{service.name}</Card.Title>
				</Card.Header>
				<Card.Content>
					{#each service.services as status}
						<div class="flex items-center gap-2">
							<span
								class={clsx('h-3 w-3 rounded-full', {
									'bg-green-500': status.status,
									'bg-red-500': !status.status
								})}
							></span>
							<p class="text-sm lg:text-base">{status.name}</p>
						</div>
					{/each}
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
		<div class="no-scrollbar mt-4 flex flex-wrap overflow-x-auto px-1 lg:p-0">
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

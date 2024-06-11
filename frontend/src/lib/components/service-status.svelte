<script lang="ts">
	import { Separator } from '$lib/components/ui/separator';
	import { Check, X } from 'lucide-svelte';

	const servicesObject: Record<string, string> = {
		symlinklibrary: 'Symlink Library',
		plexlibrary: 'Plex Library',
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
		mediafusion: 'Mediafusion',
		symlink: 'Symlink',
		plexupdater: 'Plex Updater',
		realdebrid: 'Real Debrid',
		torbox_downloader: 'Torbox Downloader'
	};

	const coreServices = ['symlinklibrary', 'plexlibrary', 'symlink'];
	const downloaderServices = ['realdebrid', 'torbox', 'torbox_downloader'];
	const contentServices = ['mdblist', 'overseerr', 'plex_watchlist', 'listrr', 'trakt'];
	const scrapingServices = [
		'torrentio',
		'knightcrawler',
		'annatar',
		'jackett',
		'orionoid',
		'mediafusion',
		'torbox'
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

	export let data: Record<string, boolean>;
	const coreServicesData = sortServices(coreServices, data);
	const downloaderServicesData = sortServices(downloaderServices, data);
	const contentServicesData = sortServices(contentServices, data);
	const scrapingServicesData = sortServices(scrapingServices, data);

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

	const servicesStatus = [
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
</script>

<div class="flex flex-col items-start">
	{#each servicesStatus as status}
		<h2 class="text-base md:text-lg">{status.name}</h2>
		{#each status.services as service}
			<div class="flex items-center gap-1">
				{#if service.status}
					<Check class="h-4 w-4 text-green-500" />
				{:else}
					<X class="h-4 w-4 text-red-500" />
				{/if}
				<p class="text-muted-foreground">{service.name}</p>
			</div>
		{/each}
		<Separator class="my-2" />
	{/each}
</div>

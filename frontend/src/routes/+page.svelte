<script lang="ts">
	import type { PageData } from './$types';
	import { formatRDDate, formatWords } from '$lib/helpers';
	import ServiceStatus from '$lib/components/service-status.svelte';
	import { Separator } from '$lib/components/ui/separator';
	import { Loader2, Check, X } from 'lucide-svelte';

	export let data: PageData;

	const MandatoryServices = ['plexlibrary', 'scraping', 'realdebrid', 'symlinklibrary'];
	const ContentServices = ['mdblist', 'overseerr', 'plex_watchlist'];
	const ScrapingServices = ['torrentio', 'annatar', 'jackett', 'orionoid'];

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
</script>

<svelte:head>
	<title>Iceberg | Home</title>
</svelte:head>

<div class="flex flex-col w-full p-8 font-medium md:px-24 lg:px-32">
	{#if 'error' in data.user || !data.user}
		<p class="text-red-500">Failed to fetch user data.</p>
		<p class="text-red-500">Error: {data.user?.error || 'Unknown'}</p>
	{:else}
		<h1 class="text-lg font-semibold md:text-xl">Welcome {data.user?.username}</h1>
		<p class="text-muted-foreground">{data.user?.email}</p>
		<p class="break-words text-muted-foreground">
			Premium expires on {formatRDDate(data.user?.expiration, 'short')}
		</p>
	{/if}
	<Separator class="my-4" />

	{#await data.services}
		<div class="flex items-center gap-1 mt-2">
			<Loader2 class="w-4 h-4 animate-spin" />
			<p class="text-muted-foreground">Fetching services status</p>
		</div>
	{:then services}
		<h2 class="text-lg font-semibold md:text-xl">Core services</h2>
		<ServiceStatus statusData={sortServices(MandatoryServices, services.data)} />
		<br />
		<h2 class="text-lg font-semibold md:text-xl">Content services</h2>
		<ServiceStatus statusData={sortServices(ContentServices, services.data)} />
		<br />
		<h2 class="text-lg font-semibold md:text-xl">Scraping services</h2>
		<ServiceStatus statusData={sortServices(ScrapingServices, services.data)} />
	{:catch}
		<p class="text-muted-foreground">Failed to fetch services status</p>
	{/await}
</div>

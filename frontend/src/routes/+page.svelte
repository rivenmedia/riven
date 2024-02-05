<script lang="ts">
	import type { PageData } from './$types';
	import { formatRDDate, formatWords } from '$lib/helpers';
	import ServiceStatus from '$lib/components/service-status.svelte';
	import { Separator } from '$lib/components/ui/separator';
	import { Loader2, Check, X } from 'lucide-svelte';

	export let data: PageData;

	const MandatoryServices = ['plex', 'content', 'scraper', 'real_debrid', 'symlink'];
	const ContentServices = ['mdblist', 'overseerr', 'plex_watchlist'];
	const ScraperServices = ['torrentio', 'jackett', 'orionoid'];

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

<div class="flex flex-col w-full p-8 md:px-24 lg:px-32 font-medium">
	{#if 'error' in data.user || !data.user}
		<p class="text-red-500">Failed to fetch user data.</p>
		<p class="text-red-500">Error: {data.user?.error || 'Unknown'}</p>
	{:else}
		<h1 class="text-lg md:text-xl font-semibold">Welcome {data.user?.username}</h1>
		<p class="text-muted-foreground">{data.user?.email}</p>
		<p class="text-muted-foreground break-words">
			Premium expires on {formatRDDate(data.user?.expiration, 'short')}
		</p>
	{/if}
	<Separator class="my-4" />

	{#await data.services}
		<div class="flex gap-1 items-center mt-2">
			<Loader2 class="w-4 h-4 animate-spin" />
			<p class="text-muted-foreground">Fetching services status</p>
		</div>
	{:then services}
		<h2 class="text-lg md:text-xl font-semibold">Core services</h2>
		<ServiceStatus statusData={sortServices(MandatoryServices, services.data)} />
		<br />
		<h2 class="text-lg md:text-xl font-semibold">Content services</h2>
		<ServiceStatus statusData={sortServices(ContentServices, services.data)} />
		<br />
		<h2 class="text-lg md:text-xl font-semibold">Scraper services</h2>
		<ServiceStatus statusData={sortServices(ScraperServices, services.data)} />
	{:catch}
		<p class="text-muted-foreground">Failed to fetch services status</p>
	{/await}
</div>

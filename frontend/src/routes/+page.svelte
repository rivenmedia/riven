<script lang="ts">
	import type { PageData } from './$types';
	import { formatRDDate, formatWords } from '$lib/helpers';
	import ServiceStatus from '$lib/components/service-status.svelte';
	import type { UserResponse } from '$lib/types';
	import { Separator } from '$lib/components/ui/separator';
	import { Loader2, Check, X } from 'lucide-svelte';

	export let data: PageData;

	const MandatoryServices = ["plex", "content", "scrape", "realdebrid", "symlink"]
	const ContentServices = ["mdblist", "overseerr"]
	const ScrapingServices = ["torrentio", "jackett", "orionoid"]

	function sortServices(services: string[], data: Record<string, boolean>) {
		let sortedData = {} as Record<string, boolean>;

		for ( let service of services) {
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

<div class="flex flex-col w-full p-8 md:px-24 lg:px-32">
	<h1 class="text-xl md:text-2xl font-semibold">Welcome {data.user?.username}</h1>
	<p class="md:text-lg text-muted-foreground">{data.user?.email}</p>
	<p class="md:text-lg text-muted-foreground break-words">
		Premium expires on {formatRDDate(data.user?.expiration, 'short')}
	</p>
	<Separator class="my-4" />

	{#await data.services}
		<div class="flex gap-1 items-center mt-2">
			<Loader2 class="w-4 h-4 animate-spin" />
			<p class="md:text-lg text-muted-foreground">Fetching services status</p>
		</div>
	{:then services}
		<h2 class="text-xl md:text-2xl font-semibold">Core services</h2>
		<ServiceStatus statusData={sortServices(MandatoryServices, services.data)} />
		<br>
		<h2 class="text-xl md:text-2xl font-semibold">Content services</h2>
		<ServiceStatus statusData={sortServices(ContentServices, services.data)} />
		<br>
		<h2 class="text-xl md:text-2xl font-semibold">Scraping services</h2>
		<ServiceStatus statusData={sortServices(ScrapingServices, services.data)} />
	{:catch}
		<p class="md:text-lg text-muted-foreground">Failed to fetch services status</p>
	{/await}

</div>

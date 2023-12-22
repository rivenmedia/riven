<script lang="ts">
	import type { PageData } from './$types';
	import { formatRDDate, formatWords } from '$lib/helpers';
	import type { UserResponse, IcebergServices } from '$lib/types';
	import { Separator } from '$lib/components/ui/separator';
	import { Loader2, Check, X } from 'lucide-svelte';

	type ServiceResponse = {
		success: boolean;
		data: IcebergServices;
	};

	export let data: PageData;

	function checkConfiguration(data: IcebergServices) {
		const fieldsToCheck: { [key: string]: string } = {
			plex: 'url',
			mdblist: 'api_key',
			overseerr: 'url',
			realdebrid: 'api_key',
			torrentio: 'filter'
		};

		const servicesStatus: { [key: string]: boolean } = {
			plex: false,
			mdblist: false,
			overseerr: false,
			realdebrid: false,
			torrentio: false
		};

		for (let key in fieldsToCheck) {
			const serviceData = (data as any)[key];
			if (
				serviceData &&
				(serviceData[fieldsToCheck[key]] === null || serviceData[fieldsToCheck[key]] === '')
			) {
				servicesStatus[key] = false;
			} else {
				servicesStatus[key] = true;
			}
		}

		return servicesStatus as Record<string, boolean>;
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
	<h2 class="text-xl md:text-2xl font-semibold">Services status</h2>
	<p class="md:text-lg text-muted-foreground">These are the services that are currently running.</p>

	{#await data.services}
		<div class="flex gap-1 items-center mt-2">
			<Loader2 class="w-4 h-4 animate-spin" />
			<p class="md:text-lg text-muted-foreground">Fetching services status</p>
		</div>
	{:then services}
		{@const servicesStatus = checkConfiguration(services.data)}
		<div class="flex flex-col gap-2 items-start mt-2">
			{#each Object.keys(servicesStatus) as serviceStatus}
				<div class="flex gap-1 items-center">
					{#if servicesStatus[serviceStatus]}
						<div class="p-1 bg-green-500 rounded-full">
							<Check class="w-4 h-4 text-white" />
						</div>
						<p class="md:text-lg text-muted-foreground">
							<span class="font-semibold">{formatWords(serviceStatus)}</span> is configured
						</p>
					{:else}
						<div class="p-1 bg-red-500 rounded-full">
							<X class="w-4 h-4 text-white" />
						</div>
						<p class="md:text-lg text-muted-foreground">
							<span class="font-semibold">{formatWords(serviceStatus)}</span> is not configured
						</p>
					{/if}
				</div>
			{/each}
		</div>
	{:catch}
		<p class="md:text-lg text-muted-foreground">Failed to fetch services status</p>
	{/await}
</div>

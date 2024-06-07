<script lang="ts">
	import type { PageData } from './$types';
	import { formatRDDate } from '$lib/helpers';
	import { Separator } from '$lib/components/ui/separator';
	import { Loader2, Check, X } from 'lucide-svelte';
	import ServiceStatus from '$lib/components/service-status.svelte';

	export let data: PageData;
</script>

<svelte:head>
	<title>Iceberg | Home</title>
</svelte:head>

<div class="flex w-full flex-col p-8 font-medium md:px-24 lg:px-32">
	{#if 'error' in data.user || !data.user}
		<p class="text-red-500">Failed to fetch user data.</p>
		<p class="text-red-500">Error: {data.user?.error || 'Unknown'}</p>
	{:else}
		<!-- <h1 class="text-xl md:text-2xl font-bold text-primary">Iceberg v{data.version.data.version}</h1> -->
		<!-- <h1 class="text-lg font-bold md:text-xl">Welcome {data.user?.username}</h1> -->
		<h1 class="text-primary text-xl font-bold md:text-2xl">
			Welcome {data.user?.username} (v{data.version.data.version})
		</h1>
		<p class="mt-2">{data.user?.email}</p>
		<p class="break-words">
			Premium expires on {formatRDDate(data.user?.expiration, 'short')} ({formatRDDate(data.user?.expiration, 'left')})
		</p>
	{/if}
	<Separator class="my-4" />

	{#await data.services}
		<div class="mt-2 flex items-center gap-1">
			<Loader2 class="h-4 w-4 animate-spin" />
			<p class="text-muted-foreground">Fetching services status</p>
		</div>
	{:then services}
		<ServiceStatus data={services.data} />
	{:catch}
		<p class="text-muted-foreground">Failed to fetch services status</p>
	{/await}
</div>

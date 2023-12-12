<script lang="ts">
	import { formatDate } from '$lib/helpers';

	export let data;
</script>

<svelte:head>
	<title>Iceberg | Home</title>
</svelte:head>

<div class="flex flex-col w-full p-8 md:px-24 lg:px-32">
	{#if data.user}
		<h1 class="text-2xl font-semibold">Welcome {data.user?.username}</h1>
		<p class="text-lg text-muted-foreground">{data.user?.email}</p>
		<p class="text-lg text-muted-foreground break-words">
			Premium expires on {formatDate(data.user?.expiration, 'short')}
		</p>
	{:else}
		<p class="text-lg text-muted-foreground">You are not logged in.</p>
	{/if}
</div>

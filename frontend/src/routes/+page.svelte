<script lang="ts">
	import { formatDate } from '$lib/helpers';
	import type { UserResponse } from '$lib/types';

	interface ExportedData {
		user: UserResponse;
	}

	export let data: ExportedData;
</script>

<svelte:head>
	<title>Iceberg | Home</title>
</svelte:head>

<div class="flex flex-col w-full p-8 md:px-24 lg:px-32">
		<h1 class="text-xl md:text-2xl font-semibold">Welcome {data.user?.username}</h1>
		<p class="md:text-lg text-muted-foreground">{data.user?.email}</p>
		<p class="md:text-lg text-muted-foreground break-words">
			Premium expires on {formatDate(data.user?.expiration, 'short')}
		</p>
</div>

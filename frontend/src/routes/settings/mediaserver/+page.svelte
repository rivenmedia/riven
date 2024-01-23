<script lang="ts">
	import type { PageData } from './$types';
	import MediaServerForm from '$lib/forms/media-server-form.svelte';
	export let data: PageData;
</script>

<div class="flex flex-col">
	<h2 class="text-2xl md:text-3xl font-semibold">Media Server Settings</h2>
	<p class="text-base md:text-lg text-muted-foreground">
		Configure media server settings for Iceberg.
	</p>

	<MediaServerForm data={data.form} actionUrl="/settings/mediaserver" />
</div>

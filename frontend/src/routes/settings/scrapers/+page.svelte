<script lang="ts">
	import type { PageData } from './$types';
	import ScrapersForm from '$lib/forms/scrapers-form.svelte';

	export let data: PageData;
</script>

<div class="flex flex-col">
	<h2 class="text-2xl md:text-3xl font-semibold">Scraper Settings</h2>
	<p class="text-base md:text-lg text-muted-foreground">Configure scraper settings for Iceberg.</p>

	<ScrapersForm data={data.form} />
</div>

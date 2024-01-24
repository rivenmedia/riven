<script lang="ts">
	import type { PageData } from './$types';
	import ScrapersForm from '$lib/forms/scrapers-form.svelte';
	import ScrapersForm from '$lib/forms/scrapers-form.svelte';

	export let data: PageData;
</script>

<div class="flex flex-col">
	<h2 class="text-xl md:text-2xl font-semibold">Scraper Settings</h2>
	<p class="text-sm md:text-base text-muted-foreground">Configure scraper settings for Iceberg.</p>

	<ScrapersForm data={data.form} actionUrl="/settings/scrapers"/>
</div>

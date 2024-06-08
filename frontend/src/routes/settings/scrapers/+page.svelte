<script lang="ts">
	import type { PageData } from './$types';
	import ScrapersForm from '$lib/forms/scrapers-form.svelte';

	export let data: PageData;
</script>

<div class="flex flex-col">
	<h2 class="text-xl font-semibold md:text-2xl">Scrapers Settings</h2>
	<p class="text-muted-foreground text-sm md:text-base">Configure scraper settings for Iceberg</p>

	<ScrapersForm data={data.form} actionUrl="/settings/scrapers" />
</div>

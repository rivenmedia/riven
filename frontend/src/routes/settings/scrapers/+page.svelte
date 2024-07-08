<script lang="ts">
	import type { PageData } from './$types';
	import ScrapersForm from '$lib/forms/scrapers-form.svelte';

	export let data: PageData;
</script>

<div class="flex flex-col">
	<h2 class="text-xl font-semibold md:text-2xl">Scraper Settings</h2>
	<p class="text-sm text-muted-foreground md:text-base">Configure scraper settings for Riven</p>

	<ScrapersForm data={data.form} actionUrl="/settings/scrapers" />
</div>

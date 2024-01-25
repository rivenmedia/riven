<script lang="ts">
	import type { PageData } from './$types';
	import ContentForm from '$lib/forms/content-form.svelte';

	export let data: PageData;
</script>

<div class="flex flex-col">
	<h2 class="text-xl md:text-2xl font-semibold">Content Settings</h2>
	<p class="text-sm md:text-base text-muted-foreground">Configure content providers for Iceberg.</p>

	<ContentForm data={data.form} actionUrl="/settings/content" />
</div>

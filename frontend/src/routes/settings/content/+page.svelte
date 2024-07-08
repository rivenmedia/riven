<script lang="ts">
	import type { PageData } from './$types';
	import ContentForm from '$lib/forms/content-form.svelte';

	export let data: PageData;
</script>

<div class="flex flex-col">
	<h2 class="text-xl font-medium md:text-2xl">Content Settings</h2>
	<p class="text-sm text-muted-foreground md:text-base">Configure content providers for Riven.</p>

	<ContentForm data={data.form} actionUrl="/settings/content" />
</div>

<script lang="ts">
	import type { PageData } from './$types';
	import GeneralForm from '$lib/forms/general-form.svelte';

	export let data: PageData;
</script>

<div class="flex flex-col">
	<h2 class="text-xl font-semibold md:text-2xl">General Settings</h2>
	<p class="text-muted-foreground text-sm md:text-base">
		Configure global and default settings for Iceberg.
	</p>

	<GeneralForm data={data.form} actionUrl="/settings/general" />
</div>

<script lang="ts">
	import type { PageData } from './$types';
	import GeneralForm from '$lib/forms/general-form.svelte';

	export let data: PageData;
</script>

<div class="flex flex-col">
	<h2 class="text-xl md:text-2xl font-semibold">General Settings</h2>
	<p class="text-sm md:text-base text-muted-foreground">
		Configure global and default settings for Iceberg.
	</p>

	<p class="text-sm text-muted-foreground">
		<small class="text-sm text-muted-foreground"
			>Fields marked with <span class="text-red-500">*</span> require restart of backend services.</small
		>
	</p>

	<GeneralForm data={data.form} actionUrl="/settings/general" />
</div>

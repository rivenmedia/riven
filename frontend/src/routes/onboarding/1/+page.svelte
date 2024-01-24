<script lang="ts">
	import type { PageData } from './$types';
	import GeneralForm from '$lib/forms/general-form.svelte';
	import { Separator } from '$lib/components/ui/separator';

	export let data: PageData;
</script>

<div class="flex flex-col p-8 md:px-24 lg:px-32 overflow-x-hidden h-full w-full py-32 items-center">
	<div class="flex flex-col items-start w-full max-w-6xl">
		<h1 class="text-3xl md:text-2xl lg:text-5xl font-bold mb-2">Step 1/4</h1>
		<p class="text-lg">Let's get started by configuring your general settings.</p>
		<small class="text-sm md:text-base text-muted-foreground"
			>Fields marked with <span class="text-red-500">*</span> require restart of backend services.</small
		>
	</div>
	<div class="mt-4 flex flex-col w-full max-w-6xl">
		<Separator class="mb-8" />
		<GeneralForm data={data.form} actionUrl="/settings/general?onboarding=true" />
	</div>
</div>

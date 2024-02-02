<script lang="ts">
	import type { PageData } from './$types';
    import ScrapersForm from '$lib/forms/scrapers-form.svelte';
	import { Separator } from '$lib/components/ui/separator';
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import { Progress } from '$lib/components/ui/progress';

	const formProgress = getContext<Writable<number>>('formProgress');
	formProgress.set(3);

	export let data: PageData;
</script>

<div class="flex flex-col p-8 md:px-24 lg:px-32 overflow-x-hidden h-full w-full py-32 items-center">
	<div class="flex flex-col items-start w-full max-w-6xl">
		<Progress class="w-full mb-2" max={4} value={$formProgress} />
		<h1 class="text-2xl md:text-3xl lg:text-4xl font-bold mb-2">Step 4/4</h1>
		<p class="text-base md:text-lg">Configure where to scrape content from.</p>
		<small class="text-sm text-muted-foreground"
			>Fields marked with <span class="text-red-500">*</span> require restart of backend services.</small
		>
	</div>
	<div class="mt-4 flex flex-col w-full max-w-6xl">
		<Separator class="mb-8" />
		<ScrapersForm data={data.form} actionUrl="/settings/scrapers?onboarding=true" />
	</div>
</div>

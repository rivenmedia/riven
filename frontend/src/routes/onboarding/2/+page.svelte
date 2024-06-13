<script lang="ts">
	import type { PageData } from './$types';
	import MediaServerForm from '$lib/forms/media-server-form.svelte';
	import { Separator } from '$lib/components/ui/separator';
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import { Progress } from '$lib/components/ui/progress';

	const formProgress = getContext<Writable<number>>('formProgress');
	formProgress.set(1);

	export let data: PageData;
</script>

<div class="flex h-full w-full flex-col items-center overflow-x-hidden p-8 py-32 md:px-24 lg:px-32">
	<div class="flex w-full max-w-6xl flex-col items-start">
		<Progress class="mb-2 w-full" max={4} value={$formProgress} />
		<h1 class="mb-2 text-2xl font-bold md:text-3xl lg:text-4xl">Step 2/4</h1>
		<p class="text-base md:text-lg">Time to configure your media server.</p>
	</div>
	<div class="mt-4 flex w-full max-w-6xl flex-col">
		<Separator class="mb-8" />
		<MediaServerForm data={data.form} actionUrl="/settings/mediaserver?onboarding=true" />
	</div>
</div>

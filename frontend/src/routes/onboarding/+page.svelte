<script lang="ts">
	import type { PageData } from './$types';
	import { animate, stagger, timeline } from 'motion';
	import { onMount } from 'svelte';
	import { Button } from '$lib/components/ui/button';
	import Rocket from 'lucide-svelte/icons/rocket';
	import Mountain from 'lucide-svelte/icons/mountain';

	export let data: PageData;

	let rootElement: HTMLElement;
	let inView = false;

	onMount(() => {
		const observer = new IntersectionObserver((entries) => {
			entries.forEach((entry) => {
				if (entry.isIntersecting) {
					inView = true;
					animate(
						'.slide-up',
						{ opacity: [0, 1], y: [40, 0] },
						{ duration: 0.5, delay: stagger(0.1) }
					);
					// animate(Array.from(animateOpacity), { opacity: [0, 1] }, { duration: 0.5, delay: stagger(0.1) });
					// const sequence: any = [
					// 	['.slide-up', { opacity: [0, 1], y: [40, 0] }, { duration: 0.4, delay: stagger(0.1) }],
					// 	['.animate-opacity', { opacity: [0, 1] }, { duration: 0.4, delay: stagger(0.1) }]
					// ];
					// timeline(sequence, {});
					observer.unobserve(rootElement);
				}
			});
		});

		observer.observe(rootElement);

		return () => {
			observer.unobserve(rootElement);
		};
	});
</script>

<div
	bind:this={rootElement}
	class="flex flex-col p-8 md:px-24 lg:px-32 overflow-x-hidden h-svh w-full"
>
	<div class:opacity-0={!inView} class="flex w-full items-center justify-center flex-col h-full">
		<div class="flex items-center justify-center slide-up">
			<Mountain class="w-16 h-16" />
		</div>
		
		{#if data.health.message !== true}
			<div class="flex flex-col gap-2 items-center justify-center slide-up">
				<h1 class="text-3xl font-semibold text-center">Iceberg is initializing...</h1>
				<Button class="font-semibold w-full" href="/">Go back to home</Button>
			</div>
		{:else}
			<h1 class="text-3xl font-semibold text-center slide-up">Welcome to Iceberg!</h1>
			<p
				class="text-base md:text-lg text-center text-muted-foreground slide-up max-w-lg md:max-w-2xl"
			>
				Before you can start using Iceberg, you need to configure some services first.
			</p>
			<Button class="mt-4 slide-up font-semibold w-full md:max-w-max" href="/onboarding/1">
				<Rocket class="w-4 h-4 mr-2" />
				<span>Let's go</span>
			</Button>
		{/if}
	</div>
</div>

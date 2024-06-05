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
	class="flex flex-col w-full p-8 overflow-x-hidden md:px-24 lg:px-32 h-svh"
>
	<div class:opacity-0={!inView} class="flex flex-col items-center justify-center w-full h-full">
		<div class="flex items-center justify-center slide-up">
			<Mountain class="w-16 h-16" />
		</div>

		<!-- TODO: REMOVED FOR SOMETIME -->
		<!-- {#if data.health.message !== true}
			<div class="flex flex-col items-center justify-center gap-2 slide-up">
				<h1 class="text-3xl font-semibold text-center">Iceberg is initializing...</h1>
				<Button class="w-full font-semibold" href="/">Go back to home</Button>
			</div>
		{:else} -->
		<h1 class="text-3xl font-semibold text-center slide-up">Welcome to Iceberg!</h1>
		<p
			class="max-w-lg text-base text-center md:text-lg text-muted-foreground slide-up md:max-w-2xl"
		>
			Before you can start using Iceberg, you need to configure some services first.
		</p>
		<Button class="w-full mt-4 font-semibold slide-up md:max-w-max" href="/onboarding/1">
			<Rocket class="w-4 h-4 mr-2" />
			<span>Let's go</span>
		</Button>
		<!-- {/if} -->
	</div>
</div>

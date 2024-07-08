<script lang="ts">
	import type { PageData } from './$types';
	import { animate, stagger, timeline } from 'motion';
	import { onMount } from 'svelte';
	import { Button } from '$lib/components/ui/button';
	import { Rocket, Mountain } from 'lucide-svelte';

	// export let data: PageData;

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
	class="flex h-svh w-full flex-col overflow-x-hidden p-8 md:px-24 lg:px-32"
>
	<div class:opacity-0={!inView} class="flex h-full w-full flex-col items-center justify-center">
		<div class="slide-up flex items-center justify-center">
			<Mountain class="h-16 w-16" />
		</div>

		<!-- TODO: REMOVED FOR SOMETIME -->
		<!-- {#if data.health.message !== true}
			<div class="flex flex-col items-center justify-center gap-2 slide-up">
				<h1 class="text-3xl font-semibold text-center">Riven is initializing...</h1>
				<Button class="w-full font-semibold" href="/">Go back to home</Button>
			</div>
		{:else} -->
		<h1 class="slide-up text-center text-3xl font-semibold">Welcome to Riven!</h1>
		<p
			class="slide-up max-w-lg text-center text-base text-muted-foreground md:max-w-2xl md:text-lg"
		>
			Before you can start using Riven, you need to configure some services first.
		</p>
		<Button class="slide-up mt-4 w-full font-semibold md:max-w-max" href="/onboarding/1">
			<Rocket class="mr-2 h-4 w-4" />
			<span>Let's go</span>
		</Button>
		<!-- {/if} -->
	</div>
</div>

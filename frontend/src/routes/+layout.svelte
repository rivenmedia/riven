<script lang="ts">
	import { ModeWatcher } from 'mode-watcher';
	import { Toaster } from 'svelte-sonner';
	import '../app.pcss';
	import { onMount } from 'svelte';
	import { afterNavigate, beforeNavigate, goto } from '$app/navigation';
	import NProgress from 'nprogress';
	import Header from '$lib/components/header.svelte';
	import * as Command from '$lib/components/ui/command';
	import { Settings, CircleDashed, SlidersHorizontal, Info, Layers, Tv } from 'lucide-svelte';

	let initializing =
		typeof localStorage !== 'undefined' ? localStorage.getItem('initialized') !== 'true' : true;

	beforeNavigate(() => {
		NProgress.start();
	});
	afterNavigate(() => {
		NProgress.done();
	});
	NProgress.configure({
		showSpinner: false
	});

	let open = false;

	onMount(() => {
		if (initializing) {
			const intervalId = setInterval(async () => {
				const response = await fetch('http://127.0.0.1:8080/health');
				if (response.ok) {
					const data = await response.json();
					console.log(data);
					initializing = data.message !== true;
					if (!initializing) {
						localStorage.setItem('initialized', 'true');
						location.reload(); // Refresh the page once the app is initialized
						clearInterval(intervalId); // Stop polling once the app is initialized
					}
				}
			}, 2000); // Poll every second

			return () => {
				clearInterval(intervalId); // Clear the interval when the component is unmounted
			};
		}
		function handleKeydown(e: KeyboardEvent) {
			if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
				e.preventDefault();
				open = !open;
			}
		}
		document.addEventListener('keydown', handleKeydown);
		return () => {
			document.removeEventListener('keydown', handleKeydown);
		};
	});
</script>

<ModeWatcher track={true} />
<Toaster richColors closeButton />

{#if initializing}
	<div
		class="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-24 h-24 flex items-center justify-center"
	>
		<div
			class="border-t-4 border-white rounded-full w-full h-full animate-spin"
			style="mask-image: linear-gradient(to right, transparent, white);"
		></div>
		<div class="font-primary text-lg absolute">Initializing</div>
	</div>
{:else}
	<Header />
	<slot />
{/if}

<Command.Dialog bind:open>
	<Command.Input class="text-base lg:text-lg font-primary" placeholder="Type a command or search..." />
	<Command.List class="font-primary">
		<Command.Empty class="lg:text-base">No results found.</Command.Empty>
		<Command.Group heading="Suggestions">
			<Command.Item
				class="lg:text-base"
				onSelect={async () => {
					open = false;
					await goto('/settings');
				}}
			>
				<Settings class="mr-2 h-4 w-4" />
				<span>Settings</span>
			</Command.Item>
			<Command.Item
				class="lg:text-base"
				onSelect={async () => {
					open = false;
					await goto('/status');
				}}
			>
				<CircleDashed class="mr-2 h-4 w-4" />
				<span>Status</span>
			</Command.Item>
		</Command.Group>
		<Command.Separator />
		<Command.Group heading="Settings">
			<Command.Item
				class="lg:text-base"
				onSelect={async () => {
					open = false;
					await goto('/settings/general');
				}}
			>
				<SlidersHorizontal class="mr-2 h-4 w-4" />
				<span>General</span>
			</Command.Item>
			<Command.Item
				class="lg:text-base"
				onSelect={async () => {
					open = false;
					await goto('/settings/plex');
				}}
			>
				<Tv class="mr-2 h-4 w-4" />
				<span>Plex</span>
			</Command.Item>
			<Command.Item
				class="lg:text-base"
				onSelect={async () => {
					open = false;
					await goto('/settings/content');
				}}
			>
				<Layers class="mr-2 h-4 w-4" />
				<span>Content</span>
			</Command.Item>
			<Command.Item
				class="lg:text-base"
				onSelect={async () => {
					open = false;
					await goto('/settings/about');
				}}
			>
				<Info class="mr-2 h-4 w-4" />
				<span>About</span>
			</Command.Item>
		</Command.Group>
	</Command.List>
</Command.Dialog>

<style>
	@keyframes spin {
		0% {
			transform: rotate(0deg);
		}
		100% {
			transform: rotate(360deg);
		}
	}
</style>

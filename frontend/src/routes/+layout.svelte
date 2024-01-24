<script lang="ts">
	import { ModeWatcher } from 'mode-watcher';
	import { Toaster } from '$lib/components/ui/sonner';
	import '../app.pcss';
	import { onMount } from 'svelte';
	import { afterNavigate, beforeNavigate, goto } from '$app/navigation';
	import NProgress from 'nprogress';
	import Header from '$lib/components/header.svelte';
	import * as Command from '$lib/components/ui/command';
	import { Settings, CircleDashed, SlidersHorizontal, Info, Layers, Tv } from 'lucide-svelte';
	import { page } from '$app/stores';
	import { setContext } from 'svelte';
	import { dev } from '$app/environment';

	setContext('formDebug', dev);

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

<div class="font-primary flex flex-col w-full h-full overflow-x-hidden">
	{#if !$page.url.pathname.startsWith('/onboarding')}
		<Header />
	{/if}
	<slot />
</div>

<Command.Dialog bind:open>
	<Command.Input
		class="text-base lg:text-lg font-primary"
		placeholder="Type a command or search..."
	/>
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

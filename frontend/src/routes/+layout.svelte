<script lang="ts">
	import { ModeWatcher } from 'mode-watcher';
	import { Toaster } from '$lib/components/ui/sonner';
	import { Toaster } from '$lib/components/ui/sonner';
	import '../app.pcss';
	import { onMount } from 'svelte';
	import { afterNavigate, beforeNavigate, goto } from '$app/navigation';
	import NProgress from 'nprogress';
	import Header from '$lib/components/header.svelte';
	import * as Command from '$lib/components/ui/command';
	import { Settings, CircleDashed, SlidersHorizontal, Info, Layers, Tv } from 'lucide-svelte';
	import type { ComponentType } from 'svelte';
	import type { Icon } from 'lucide-svelte';
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

	type CommandItem = {
		name: string;
		href: string;
		icon: ComponentType<Icon>;
	};

	const suggestedItems: CommandItem[] = [
		{
			name: 'Settings',
			href: '/settings',
			icon: Settings
		},
		{
			name: 'Status',
			href: '/status',
			icon: CircleDashed
		}
	];

	const commandItems: CommandItem[] = [
		{
			name: 'General',
			href: '/settings/general',
			icon: SlidersHorizontal
		},
		{
			name: 'Media Server',
			href: '/settings/mediaserver',
			icon: Tv
		},
		{
			name: 'Content',
			href: '/settings/content',
			icon: Layers
		},
		{
			name: 'Scrapers',
			href: '/settings/scrapers',
			icon: Layers
		},
		{
			name: 'About',
			href: '/settings/about',
			icon: Info
		}
	];
</script>

<ModeWatcher track={true} />
<Toaster richColors closeButton />

<div class="font-primary font-medium flex flex-col w-full h-full overflow-x-hidden">
	{#if !$page.url.pathname.startsWith('/onboarding')}
		<Header />
	{/if}
	<slot />
</div>

<Command.Dialog bind:open>
	<Command.Input
		class="font-medium font-primary"
		placeholder="Type a command or search..."
	/>
	<Command.List class="font-primary font-medium">
		<Command.Empty>No results found.</Command.Empty>
		<Command.Group heading="Suggestions">
			{#each suggestedItems as item}
				<Command.Item
					class="text-sm"
					onSelect={async () => {
						open = false;
						await goto(item.href);
					}}
				>
					<svelte:component this={item.icon} class="mr-2 h-4 w-4" />
					<span>{item.name}</span>
				</Command.Item>
			{/each}
		</Command.Group>
		<Command.Separator />
		<Command.Group heading="All">
			{#each commandItems as item}
				<Command.Item
					class="text-sm"
					onSelect={async () => {
						open = false;
						await goto(item.href);
					}}
				>
					<svelte:component this={item.icon} class="mr-2 h-4 w-4" />
					<span>{item.name}</span>
				</Command.Item>
			{/each}
		</Command.Group>
	</Command.List>
</Command.Dialog>

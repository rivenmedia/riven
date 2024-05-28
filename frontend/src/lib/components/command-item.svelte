<script lang="ts">
    import { Settings, CircleDashed, SlidersHorizontal, Info, Layers, Tv } from 'lucide-svelte';
	import type { ComponentType } from 'svelte';
	import type { Icon } from 'lucide-svelte';
    import * as Command from '$lib/components/ui/command';
    import { onMount } from 'svelte';
    import { goto } from '$app/navigation';
	import { commandPalette } from '$lib/stores';

    onMount(() => {
		function handleKeydown(e: KeyboardEvent) {
			if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
				e.preventDefault();
				commandPalette.set(true);
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

<Command.Dialog bind:open={$commandPalette}>
	<Command.Input class="font-medium font-primary" placeholder="Type a command or search..." />
	<Command.List class="font-medium font-primary">
		<Command.Empty>No results found.</Command.Empty>
		<Command.Group heading="Suggestions">
			{#each suggestedItems as item}
				<Command.Item
					class="text-sm"
					onSelect={async () => {
						commandPalette.set(false);
						await goto(item.href);
					}}
				>
					<svelte:component this={item.icon} class="w-4 h-4 mr-2" />
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
						commandPalette.set(false);
						await goto(item.href);
					}}
				>
					<svelte:component this={item.icon} class="w-4 h-4 mr-2" />
					<span>{item.name}</span>
				</Command.Item>
			{/each}
		</Command.Group>
	</Command.List>
</Command.Dialog>
<script lang="ts">
	import type { NavItem } from '$lib/types';
	import ThemeSwitcher from '$lib/components/theme-switcher.svelte';
	import NavigationItem from '$lib/components/header-item.svelte';
	import { Mountain, MoreHorizontal, X, Command } from 'lucide-svelte';
	import { Button } from '$lib/components/ui/button';
	import CommandItem from '$lib/components/command-item.svelte';
	import { commandPalette } from '$lib/stores';

	const navItems: NavItem[] = [
		{
			name: 'Home',
			path: '/'
		},
		{
			name: 'Status',
			path: '/status'
		},
		{
			name: 'Settings',
			path: '/settings'
		}
	];

	let showMenu = false;

	function toggleCommand() {
		$commandPalette = !$commandPalette;
	}

	function toggleNavbar() {
		showMenu = !showMenu;
	}
</script>

<header class="flex items-center justify-between w-full p-8 md:px-24 lg:px-32">
	<div class="flex items-center gap-2">
		<a href="/" class="flex items-center gap-2">
			<Mountain class="size-6 md:size-8" />
			<h1 class="text-xl font-semibold md:text-2xl">Iceberg</h1>
		</a>
		<Button
			class="items-center hidden p-2 px-4 ml-2 text-sm font-medium rounded-md lg:flex"
			type="button"
			on:click={toggleCommand}
		>
			<div class="flex items-center">
				<Command class="w-4 h-4" />
				<span>K</span>
			</div>
			<span class="ml-2">to open command palette</span>
		</Button>
	</div>
	<nav class="items-center hidden gap-6 tracking-wider md:flex">
		<div class="flex items-center gap-3">
			{#each navItems as navItem}
				<NavigationItem {navItem} />
			{/each}
		</div>
		<ThemeSwitcher />
	</nav>
	<nav class="flex items-center gap-2 tracking-wider md:hidden">
		<ThemeSwitcher />
		<Button on:click={toggleNavbar} type="button" size="sm" class="max-w-max">
			<MoreHorizontal class="w-4 h-4" />
		</Button>
	</nav>
</header>

<div
	id="mobilenav"
	class:h-0={!showMenu}
	class:h-screen={showMenu}
	class:h-[100dvh]={showMenu}
	class="h-0 w-screen fixed z-[99] top-0 left-0 bg-background overflow-x-hidden flex flex-col items-center md:hidden"
>
	<div class="flex items-end justify-end w-full p-8 transition-all duration-300 ease-in-out">
		<Button on:click={toggleNavbar} type="button" size="sm" class="max-w-max">
			<X class="w-4 h-4" />
		</Button>
	</div>
	<div class="flex flex-col items-center justify-center w-full gap-6 p-8">
		{#each navItems as navItem}
			<button on:click={toggleNavbar}>
				<NavigationItem {navItem} />
			</button>
		{/each}
	</div>
</div>

<CommandItem bind:open={$commandPalette}/>

<style>
	#mobilenav {
		transition: all 0.5s ease-in-out;
	}
</style>

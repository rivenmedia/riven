<script lang="ts">
	import type { NavItem } from '$lib/types';
	import ThemeSwitcher from '$lib/components/theme-switcher.svelte';
	import NavigationItem from '$lib/components/header/item.svelte';
	import { Mountain, MoreHorizontal, X } from 'lucide-svelte';
	import { Button } from '$lib/components/ui/button';

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

	function toggleNavbar() {
		showMenu = !showMenu;
	}
</script>

<header class="flex items-center justify-between w-full p-8 md:px-24 lg:px-32">
	<a href="/" class="flex items-center gap-2">
		<Mountain class="h-8 w-8" />
		<h1 class="text-3xl font-semibold tracking-wider">Iceberg</h1>
	</a>
	<nav class="items-center gap-6 tracking-wider hidden md:flex">
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
			<MoreHorizontal class="h-4 w-4" />
		</Button>
	</nav>	
</header>

<div
	id="mobilenav"
	class:h-0={!showMenu}
	class:h-screen={showMenu}
	class:h-[100dvh]={showMenu}
	class="h-0 w-screen fixed z-10 top-0 left-0 bg-background overflow-x-hidden flex flex-col items-center md:hidden"
>
	<div class="flex p-10 w-full items-end justify-end transition-all ease-in-out duration-300">
		<Button on:click={toggleNavbar} type="button" size="sm" class="max-w-max">
			<X class="h-4 w-4" />
		</Button>
	</div>
	<div class="flex flex-col items-center justify-center gap-6 p-8 w-full">
		{#each navItems as navItem}
			<NavigationItem {navItem} />
		{/each}
	</div>
</div>

<style>
	#mobilenav {
		transition: all 0.5s ease-in-out;
	}
</style>
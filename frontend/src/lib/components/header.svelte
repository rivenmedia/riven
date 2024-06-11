<script lang="ts">
	import type { NavItem } from '$lib/types';
	import ThemeSwitcher from '$lib/components/theme-switcher.svelte';
	import NavigationItem from '$lib/components/header-item.svelte';
	import { Mountain, MoreHorizontal, X, Command } from 'lucide-svelte';
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

<header class="flex w-full items-center justify-between border-b p-8 md:px-24 lg:px-32">
	<div class="flex items-center gap-2">
		<a href="/" class="flex items-center gap-2">
			<Mountain class="size-6 md:size-8" />
			<h1 class="text-xl font-semibold md:text-2xl">Riven</h1>
		</a>
	</div>
	<nav class="hidden items-center gap-6 tracking-wider md:flex">
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
	class="fixed left-0 top-0 z-[99] flex h-0 w-screen flex-col items-center overflow-x-hidden bg-background md:hidden"
>
	<div class="flex w-full items-end justify-end p-8 transition-all duration-300 ease-in-out">
		<Button on:click={toggleNavbar} type="button" size="sm" class="max-w-max">
			<X class="h-4 w-4" />
		</Button>
	</div>
	<div class="flex w-full flex-col items-center justify-center gap-6 p-8">
		{#each navItems as navItem}
			<button on:click={toggleNavbar}>
				<NavigationItem {navItem} />
			</button>
		{/each}
	</div>
</div>

<style>
	#mobilenav {
		transition: all 0.5s ease-in-out;
	}
</style>

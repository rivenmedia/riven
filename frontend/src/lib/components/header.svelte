<script lang="ts">
	import type { NavItem } from '$lib/types';
	import ThemeSwitcher from '$lib/components/theme-switcher.svelte';
	import NavigationItem from '$lib/components/header-item.svelte';
	import { Mountain, MoreHorizontal, X, Command } from 'lucide-svelte';
	import { Button } from '$lib/components/ui/button';
	import clsx from 'clsx';
	import * as Drawer from '$lib/components/ui/drawer';
	import { getContext } from 'svelte';
	import { type Writable } from 'svelte/store';
	import { goto } from '$app/navigation';
	import { onMount, onDestroy } from 'svelte';

	const navItems: NavItem[] = [
		{
			name: 'Home',
			path: '/'
		},
		{
			name: 'Summary',
			path: '/summary'
		},
		{
			name: 'Library',
			path: '/library'
		},
		{
			name: 'Settings',
			path: '/settings'
		}
	];

	let showMenu: Writable<boolean> = getContext('showMenu');

	function toggleNavbar() {
		showMenu.update((v) => !v);
	}

	export let darkWhiteText: boolean = false;

	onMount(async () => {
		const header = document.getElementById('header');
		const headerHeight = header?.offsetHeight;
		console.log(headerHeight);

		// header?.style.transition = 'padding 0.5s ease, other-properties 0.5s ease';

		window.addEventListener('scroll', () => {
			if (window.scrollY) {
				// header?.classList.add('absolute');
				header?.classList.remove('p-8');
				header?.classList.add('p-4');
				header?.classList.add('backdrop-blur-sm');
			} else {
				// header?.classList.remove('absolute');
				header?.classList.remove('p-4');
				header?.classList.add('p-8');
				header?.classList.remove('backdrop-blur-sm');
			}
		});
	});
</script>

<header
	id="header"
	class={clsx(
		'fixed top-0 flex w-full items-center justify-between bg-transparent p-8 transition-all duration-300 ease-in-out md:px-24 lg:px-32',
		{
			'text-background dark:text-foreground': darkWhiteText
		},
		{
			'text-foreground': !darkWhiteText
		}
	)}
>
	<div class="flex items-center gap-2">
		<a href="/" class="flex items-center gap-2">
			<Mountain class="size-6 md:size-8" />
			<h1 class="text-xl font-medium md:text-2xl">Riven</h1>
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
		<Drawer.Root
			onClose={() => {
				showMenu.set(false);
			}}
			open={$showMenu}
		>
			<Drawer.Trigger>
				<Button type="button" size="sm" class="max-w-max">
					<MoreHorizontal class="h-4 w-4" />
				</Button>
			</Drawer.Trigger>
			<Drawer.Content>
				<nav class="my-4 flex w-full flex-col items-center justify-center gap-2">
					{#each navItems as navItem}
						<Drawer.Close asChild let:builder>
							<Button
								on:click={() => {
									goto(navItem.path);
								}}
								builders={[builder]}
								size="sm"
								variant="ghost"
							>
								{navItem.name}
							</Button>
						</Drawer.Close>
					{/each}
				</nav>
			</Drawer.Content>
		</Drawer.Root>
	</nav>
</header>

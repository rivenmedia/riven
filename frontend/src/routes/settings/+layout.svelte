<script lang="ts">
	import { Separator } from '$lib/components/ui/separator';
	import * as Select from '$lib/components/ui/select';
	import type { NavItem } from '$lib/types';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import clsx from 'clsx';

	const settingsItems: NavItem[] = [
		{
			name: 'General',
			path: '/settings/general'
		},
		{
			name: 'Media Server',
			path: '/settings/mediaserver'
		},
		{
			name: 'Scrapers',
			path: '/settings/scrapers'
		},
		{
			name: 'Content',
			path: '/settings/content'
		},
		{
			name: 'About',
			path: '/settings/about'
		}
	];
</script>

<svelte:head>
	<title>Settings | General</title>
</svelte:head>

<div class="flex w-full flex-col p-8 md:px-24 lg:px-32">
	<Select.Root
		portal={null}
		onSelectedChange={(selected) => {
			goto(String(selected?.value));
		}}
		selected={{
			value: $page.url.pathname,
			label:
				(settingsItems.find((item) => item.path === $page.url.pathname) || {}).name || 'Not found'
		}}
	>
		<Select.Trigger class="w-full text-sm lg:hidden">
			<Select.Value placeholder="Select settings type" />
		</Select.Trigger>
		<Select.Content>
			{#each settingsItems as item}
				<Select.Item value={item.path} label={item.name}>{item.name}</Select.Item>
			{/each}
		</Select.Content>
	</Select.Root>

	<div class="text-foreground hidden w-full flex-wrap gap-2 rounded-md p-1 text-sm lg:flex">
		{#each settingsItems as item}
			<a
				class={clsx('rounded-md p-2 px-4 transition-all duration-300', {
					'bg-secondary text-foreground font-semibold': item.path === $page.url.pathname,
					'hover:bg-secondary text-foreground': item.path !== $page.url.pathname
				})}
				href={item.path}
			>
				{item.name}
			</a>
		{/each}
	</div>

	<Separator class="mb-4 mt-2" />

	<slot />
</div>

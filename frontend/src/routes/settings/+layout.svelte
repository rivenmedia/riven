<script lang="ts">
	import { Separator } from '$lib/components/ui/separator';
	import * as Select from '$lib/components/ui/select';
	import type { NavItem } from '$lib/types';
	import HeaderItem from '$lib/components/header-item.svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	const settingsItems: NavItem[] = [
		{
			name: 'General',
			path: '/settings/general'
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

<div class="p-8 md:px-24 lg:px-32 flex flex-col">
	<Select.Root
		onSelectedChange={(selected) => {
			goto(String(selected?.value));
		}}
		selected={{
			value: $page.url.pathname,
			label:
				(settingsItems.find((item) => item.path === $page.url.pathname) || {}).name || 'Not found'
		}}
	>
		<Select.Trigger class="text-base">
			<Select.Value placeholder="Select settings type" />
		</Select.Trigger>
		<Select.Content>
			{#each settingsItems as item}
				<Select.Item value={item.path} label={item.name}>{item.name}</Select.Item>
			{/each}
		</Select.Content>
	</Select.Root>

	<Separator class="mb-4 mt-2" />

	<slot />
</div>

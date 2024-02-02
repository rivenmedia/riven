<script lang="ts">
	import type { PageData } from './$types';
	import { Separator } from '$lib/components/ui/separator';
	import { formatWords } from '$lib/helpers';
	import * as Alert from '$lib/components/ui/alert';
	import { Button } from '$lib/components/ui/button';
	import { Loader2, MoveUpRight } from 'lucide-svelte';
	import { toast } from 'svelte-sonner';

	export let data: PageData;

	const version = data.settings.data.version;
	const host_path = data.settings.data.symlink.host_path;
	const container_path = data.settings.data.symlink.container_path;

	interface AboutData {
		[key: string]: any;
		host_path: string;
		container_path: string;
	}

	type SupportData = {
		[key: string]: any;
		github: string;
		discord: string;
	};

	const aboutData: AboutData = {
		host_path,
		container_path
	};
	const supportData: SupportData = {
		github: 'https://github.com/dreulavelle/iceberg',
		discord: 'https://discord.gg/wDgVdH8vNM'
	};

	let updateLoading = false;

	async function getLatestVersion() {
		updateLoading = true;
		const data = await fetch(
			'https://raw.githubusercontent.com/dreulavelle/iceberg/main/backend/utils/default_settings.json'
		);
		const json = await data.json();
		updateLoading = false;

		if (json.version !== version) {
			toast.warning('A new version is available! Checkout the changelog on GitHub.');
		} else {
			toast.success('You are running the latest version.');
		}
	}
</script>

<svelte:head>
	<title>Settings | About</title>
</svelte:head>

<div class="flex flex-col">
	<Alert.Root class="text-sm">
		<Alert.Title>Heads up!</Alert.Title>
		<Alert.Description class=""
			>Iceberg is in rapid development. Expect bugs and breaking changes.</Alert.Description
		>
	</Alert.Root>

	<h2 class="text-xl md:text-2xl font-semibold mt-2">About</h2>
	<p class="text-sm md:text-base text-muted-foreground mb-2">Know what you're running.</p>
	<div class="flex flex-col gap-4 w-full">
		<div class="flex flex-col md:flex-row items-start md:items-center mb-2">
			<h3 class="text-sm md:text-base font-semibold w-48 min-w-48 text-muted-foreground">
				{formatWords('Version')}
			</h3>
			<div class="flex flex-wrap gap-2 w-full">
				<p class="text-xs md:text-sm break-words p-2 rounded-md bg-secondary">
					{version}
				</p>
				<Button
					on:click={async () => {
						await getLatestVersion();
					}}
					disabled={updateLoading}
					variant="outline"
					size="sm"
				>
					{#if updateLoading}
						<Loader2 class="w-4 h-4 mr-1 animate-spin" />
					{:else}
						<MoveUpRight class="w-4 h-4 mr-1" />
					{/if}
					Check for updates
				</Button>
			</div>
		</div>
		{#each Object.keys(aboutData) as key}
			<Separator />
			<div class="flex flex-col md:flex-row items-start md:items-center mb-2">
				<h3 class="text-sm md:text-base font-semibold w-48 min-w-48 text-muted-foreground">
					{formatWords(key)}
				</h3>
				<div class="flex w-full">
					<p class="text-xs md:text-sm break-words p-2 rounded-md bg-secondary">
						{aboutData[key]}
					</p>
				</div>
			</div>
		{/each}
	</div>

	<h2 class="text-xl md:text-2xl font-semibold mt-2">Support</h2>
	<p class="text-sm md:text-base text-muted-foreground mb-2">
		Need help? Join the Discord server or open an issue on GitHub.
	</p>
	<div class="flex flex-col gap-4 w-full">
		{#each Object.keys(supportData) as key}
			<Separator />
			<div class="flex flex-col md:flex-row items-start md:items-center mb-2">
				<h3 class="text-sm md:text-base font-semibold w-48 min-w-48 text-muted-foreground">
					{formatWords(key)}
				</h3>
				<div class="flex w-full">
					<a href={supportData[key]} class="text-xs md:text-sm break-words underline">
						{supportData[key]}
					</a>
				</div>
			</div>
		{/each}
	</div>
</div>

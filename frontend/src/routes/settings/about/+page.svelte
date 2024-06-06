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
	const rclone_path = data.settings.data.symlink.rclone_path;
	const library_path = data.settings.data.symlink.library_path;

	interface AboutData {
		[key: string]: any;
		rclone_path: string;
		library_path: string;
	}

	type SupportData = {
		[key: string]: any;
		github: string;
		discord: string;
	};

	const aboutData: AboutData = {
		rclone_path,
		library_path
	};
	const supportData: SupportData = {
		discord: 'https://discord.gg/wDgVdH8vNM',
		github: 'https://github.com/dreulavelle/iceberg'
	};

	let updateLoading = false;

	async function getLatestVersion() {
		updateLoading = true;
		const data = await fetch('https://raw.githubusercontent.com/dreulavelle/iceberg/main/VERSION');
		if (data.status !== 200) {
			toast.error('Failed to fetch latest version.');
			updateLoading = false;
			return;
		}
		const remoteVersion = await data.text();
		updateLoading = false;

		if (remoteVersion !== version) {
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
	<h2 class="mt-2 text-xl font-semibold md:text-2xl">About</h2>
	<p class="mb-2 text-sm md:text-base text-muted-foreground">Know what you're running.</p>
	<div class="flex flex-col w-full gap-4">
		<div class="flex flex-col items-start mb-2 md:flex-row md:items-center">
			<h3 class="w-48 text-sm font-semibold md:text-base min-w-48 text-muted-foreground">
				{formatWords('Version')}
			</h3>
			<div class="flex flex-wrap w-full gap-2">
				<p class="p-2 text-xs break-words rounded-md md:text-sm bg-secondary">
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
			<div class="flex flex-col items-start mb-2 md:flex-row md:items-center">
				<h3 class="w-48 text-sm font-semibold md:text-base min-w-48 text-muted-foreground">
					{formatWords(key)}
				</h3>
				<div class="flex w-full">
					<p class="p-2 text-xs break-words rounded-md md:text-sm bg-secondary">
						{aboutData[key]}
					</p>
				</div>
			</div>
		{/each}
	</div>

	<h2 class="mt-2 text-xl font-semibold md:text-2xl">Support</h2>
	<p class="mb-2 text-sm md:text-base text-muted-foreground">
		Need help? Join the Discord server or open an issue on GitHub.
	</p>
	<div class="flex flex-col w-full gap-4">
		{#each Object.keys(supportData) as key}
			<Separator />
			<div class="flex flex-col items-start mb-2 md:flex-row md:items-center">
				<h3 class="w-48 text-sm font-semibold md:text-base min-w-48 text-muted-foreground">
					{formatWords(key)}
				</h3>
				<div class="flex w-full">
					<a href={supportData[key]} class="text-xs underline break-words md:text-sm">
						{supportData[key]}
					</a>
				</div>
			</div>
		{/each}
	</div>

	<h2 class="mt-2 text-xl font-semibold md:text-2xl">Contributors</h2>
	<p class="mb-2 text-sm md:text-base text-muted-foreground">
		Thanks to the following people for their contributions to Iceberg
	</p>

	<a
		href="https://github.com/dreulavelle/iceberg/graphs/contributors"
		target="_blank"
		rel="noopener noreferrer"
		><img
			alt="contributors"
			src="https://contrib.rocks/image?repo=dreulavelle/iceberg"
			class="mt-2 max-w-lg"
		/></a
	>
</div>

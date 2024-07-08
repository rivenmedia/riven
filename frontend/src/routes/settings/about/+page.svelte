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
		github: 'https://github.com/rivenmedia/riven'
	};

	let updateLoading = false;

	async function getLatestVersion() {
		updateLoading = true;
		const data = await fetch('https://raw.githubusercontent.com/rivenmedia/riven/main/VERSION');
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
	<h2 class="text-xl font-medium md:text-2xl">About</h2>
	<p class="text-muted-foreground text-sm md:text-base">
		Know what you're running and how to get help.
	</p>
	<div class="my-8 flex w-full flex-col gap-4">
		<div class="mb-2 flex flex-col items-start md:flex-row md:items-center">
			<h3 class="w-48 min-w-48 text-sm">Version</h3>
			<div class="flex w-full flex-wrap gap-2">
				<p class="bg-secondary break-words rounded-md p-2 text-sm">
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
						<Loader2 class="mr-2 h-4 w-4 animate-spin" />
					{:else}
						<MoveUpRight class="mr-2 h-4 w-4" />
					{/if}
					Check for updates
				</Button>
			</div>
		</div>
		{#each Object.keys(aboutData) as key}
			<Separator />
			<div class="mb-2 flex flex-col items-start md:flex-row md:items-center">
				<h3 class="w-48 min-w-48 text-sm">
					{formatWords(key)}
				</h3>
				<div class="flex w-full">
					<p class="bg-secondary break-words rounded-md p-2 text-sm">
						{aboutData[key]}
					</p>
				</div>
			</div>
		{/each}
	</div>

	<h2 class="text-xl font-medium md:text-2xl">Support</h2>
	<p class="text-muted-foreground text-sm md:text-base">
		Need help? Reach out to the Riven community or report an issue on GitHub.
	</p>
	<div class="my-8 flex w-full flex-col gap-4">
		{#each Object.keys(supportData) as key}
			<Separator />
			<div class="mb-2 flex flex-col items-start md:flex-row md:items-center">
				<h3 class="w-48 min-w-48 text-sm">
					{formatWords(key)}
				</h3>
				<div class="flex w-full">
					<a href={supportData[key]} class="break-words text-sm underline">
						{supportData[key]}
					</a>
				</div>
			</div>
		{/each}
	</div>

	<h2 class="text-xl font-medium md:text-2xl">Contributors</h2>
	<p class="text-muted-foreground text-sm md:text-base">
		Thanks to the following people for their contributions to Riven
	</p>
	<a
		href="https://github.com/rivenmedia/riven/graphs/contributors"
		target="_blank"
		rel="noopener noreferrer"
		class="my-8"
		><img
			alt="contributors"
			src="https://contrib.rocks/image?repo=rivenmedia/riven"
			class="mt-2 max-w-lg"
		/></a
	>
</div>

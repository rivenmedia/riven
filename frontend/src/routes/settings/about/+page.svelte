<script lang="ts">
	import type { PageData } from './$types';
	import { Separator } from '$lib/components/ui/separator';
	import { formatWords } from '$lib/helpers';
	import * as Alert from '$lib/components/ui/alert';

	export let data: PageData;

	const version = data.settings.data.version;
	const host_path = data.settings.data.symlink.host_path;
	const container_path = data.settings.data.symlink.container_path;

	interface AboutData {
		[key: string]: any;
		version: string;
		host_path: string;
		container_path: string;
	}

	type SupportData = {
		[key: string]: any;
		github: string;
		discord: string;
	};

	const aboutData: AboutData = {
		version,
		host_path,
		container_path
	};
	const supportData: SupportData = {
		github: 'https://github.com/dreulavelle/iceberg',
		discord: 'https://discord.gg/wDgVdH8vNM'
	};
</script>

<svelte:head>
	<title>Settings | About</title>
</svelte:head>

<div class="flex flex-col">
	<Alert.Root class="text-lg">
		<Alert.Title>Heads up!</Alert.Title>
		<Alert.Description class="text-base"
			>Iceberg is in rapid development. Expect bugs.</Alert.Description
		>
	</Alert.Root>

	<h2 class="text-2xl md:text-3xl font-semibold mt-2">About</h2>
	<p class="text-base md:text-lg text-muted-foreground mb-2">Know what you're running.</p>
	<div class="flex flex-col gap-4 w-full">
		{#each Object.keys(aboutData) as key}
			<Separator />
			<div class="flex flex-col md:flex-row items-start md:items-center mb-2">
				<h3 class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground">
					{formatWords(key)}
				</h3>
				<div class="flex w-full">
					<p class="text-sm md:text-base break-words p-2 rounded-md bg-slate-100 dark:bg-slate-900">
						{aboutData[key]}
					</p>
				</div>
			</div>
		{/each}
	</div>

	<h2 class="text-2xl md:text-3xl font-semibold mt-2">Support</h2>
	<p class="text-base md:text-lg text-muted-foreground mb-2">
		Need help? Join the Discord server or open an issue on GitHub.
	</p>
	<div class="flex flex-col gap-4 w-full">
		{#each Object.keys(supportData) as key}
			<Separator />
			<div class="flex flex-col md:flex-row items-start md:items-center mb-2">
				<h3 class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground">
					{formatWords(key)}
				</h3>
				<div class="flex w-full">
					<a href={supportData[key]} class="text-sm md:text-base break-words underline">
						{supportData[key]}
					</a>
				</div>
			</div>
		{/each}
	</div>
</div>

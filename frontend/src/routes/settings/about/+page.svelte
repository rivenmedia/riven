<script lang="ts">
	import { Separator } from '$lib/components/ui/separator';
	import { formatWords } from '$lib/helpers';

	export let data;

	const supportData = {
		github: 'https://github.com/dreulavelle/iceberg',
		discord: 'To be announced'
	};
</script>

<div class="flex flex-col gap-2">
	<h1 class="text-2xl md:text-3xl font-semibold mb-2">About Iceberg</h1>

	<div class="flex flex-col gap-4 w-full">
		{#each Object.keys(data.settings) as key}
			<Separator />
			<div class="flex flex-col md:flex-row items-start md:items-center mb-2">
				<h3 class="text-lg md:text-xl font-semibold w-[12rem] min-w-[12rem]">
					{formatWords(key)}
				</h3>
				<div class="flex w-full">
					<p
						class="text-base md:text-lg text-muted-foreground break-words p-2 rounded-md bg-slate-100 dark:bg-slate-900"
					>
						{data.settings[key].data}
					</p>
				</div>
			</div>
		{/each}
	</div>

	<h1 class="text-2xl md:text-3xl font-semibold mt-4 mb-2">Support</h1>

	<div class="flex flex-col gap-4 w-full">
		<Separator />
		<div class="flex flex-col md:flex-row items-start md:items-center mb-2">
			<h3 class="text-lg md:text-xl font-semibold w-[12rem] min-w-[12rem]">GitHub</h3>
			<div class="flex w-full">
				<a
					href="https://github.com/dreulavelle/iceberg"
					class="text-base md:text-lg text-muted-foreground break-words underline"
				>
					https://github.com/dreulavelle/iceberg
				</a>
			</div>
		</div>

		<Separator />
		<div class="flex flex-col md:flex-row items-start md:items-center mb-2">
			<h3 class="text-lg md:text-xl font-semibold w-[12rem] min-w-[12rem]">Discord</h3>
			<div class="flex w-full">
				<a
					href="https://discord.gg/wDgVdH8vNM"
					class="text-base md:text-lg text-muted-foreground break-words underline"
				>
					https://discord.gg/wDgVdH8vNM
				</a>
			</div>
		</div>
	</div>
</div>

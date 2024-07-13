<script lang="ts">
	export let data: any;
	export let statesName;

	// https://images.metahub.space/poster/small/tt3083016/img
	const baseUrl = 'https://images.metahub.space/poster/small/';

	const convertTo: Record<string, string> = {
		Movie: 'movie',
		Show: 'tv'
	};
</script>

<a
	class="xl:w-1/7 group relative mb-2 flex w-1/2 flex-shrink-0 flex-col gap-2 rounded-lg p-[.5rem] sm:w-1/3 md:w-1/4 lg:w-1/6"
	href="/{convertTo[data.type]}/{data.imdb_id}"
>
	<div class="relative aspect-[1/1.5] w-full overflow-hidden rounded-lg">
		<span class="inline-block h-full w-full">
			<img
				width="100%"
				alt={data.title}
				height="100%"
				src="{baseUrl}{data.imdb_id}/img"
				class="h-full w-full object-cover object-center transition-all duration-300 ease-in-out group-hover:scale-105"
			/>
		</span>
		<div
			class="absolute inset-0 z-0 flex h-full w-full flex-col justify-end gap-1 bg-gradient-to-t from-zinc-900 pb-2 tracking-wide lg:group-hover:opacity-100"
		>
			<div
				class="flex flex-wrap justify-center gap-1 text-xs font-normal tracking-wide text-gray-200 md:items-center 2xl:text-sm"
			>
				<span>{data.type}</span>
				•
				<span class="whitespace-nowrap">
					<span>{data.state === 'PartiallyCompleted' ? 'Partial' : statesName[data.state]}</span>
				</span>
			</div>
			<div class="line-clamp-2 text-center text-sm font-medium leading-tight">{data.title}</div>
		</div>
	</div>
</a>

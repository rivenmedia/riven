<script lang="ts">
	import type { PlexDebridItem } from '$lib/types';
	import { Badge } from '$lib/components/ui/badge';
	import { formatState } from '$lib/helpers';

	export let plexDebridItem: PlexDebridItem;

	let fallback = 'https://via.placeholder.com/198x228.png?text=No+thumbnail';
	let poster = `https://images.metahub.space/poster/small/${plexDebridItem.imdb_id}/img`;
	let banner = `https://images.metahub.space/background/medium/${plexDebridItem.imdb_id}/img`;
</script>

<!-- <div
	class="flex flex-col group justify-end gap-2 w-36 md:w-48 h-72 rounded-md bg-cover bg-center relative select-none"
	style="background-image: url({poster})"
>
	<img alt="test" src={poster} on:error={() => (poster = fallback)} class="hidden" />

	<div
		class="bg-black bg-opacity-60 text-white p-2 absolute bottom-0 w-full opacity-0 group-hover:opacity-100 transition-opacity duration-200"
	>
		<p class="text-base max-w-[9rem] md:max-w-[12rem]">{plexDebridItem.title}</p>
		<p class="text-sm max-w-[9rem] md:max-w-[12rem]">{plexDebridItem.aired_at}</p>
	</div>
</div> -->

<div
	class="flex flex-col md:flex-row md:justify-between gap-2 md:gap-0 text-white w-full bg-cover bg-center relative rounded-xl p-4 overflow-hidden"
	style="background-image: url({banner});"
>
	<div class="absolute top-0 left-0 w-full h-full bg-black opacity-40 rounded-xl" />
	<div class="w-full h-full flex flex-col md:flex-row gap-2">
		<div
			class="z-10 flex gap-x-2 items-start md:items-center w-full md:w-2/3"
		>
			<img
				alt="test"
				src={poster}
				on:error={() => (poster = fallback)}
				class="w-18 h-24 rounded-md"
			/>
			<div class="flex flex-col">
				<p class="text-xl font-semibold md:text-ellipsis md:line-clamp-1">{plexDebridItem.title}</p>
				<p>{plexDebridItem.aired_at}</p>
			</div>
		</div>
		<div class="z-10 flex flex-col items-start w-full md:w-1/2">
			<div class="flex gap-2 items-center">
				<p class="text-lg font-semibold">Status</p>
				<Badge>
					{formatState(plexDebridItem.state)}
				</Badge>
			</div>
		</div>
	</div>
</div>

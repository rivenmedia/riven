<script lang="ts">
	import type { PlexDebridItem, StatusInterface } from '$lib/types';
	import { Badge } from '$lib/components/ui/badge';

	export let plexDebridItem: PlexDebridItem;
	export let itemState: StatusInterface;

	let fallback = 'https://via.placeholder.com/198x228.png?text=No+thumbnail';
	let poster = `https://images.metahub.space/poster/small/${plexDebridItem.imdb_id}/img`;
	let banner = `https://images.metahub.space/background/medium/${plexDebridItem.imdb_id}/img`;
</script>

<div
	class="flex flex-col md:flex-row md:justify-between gap-2 md:gap-0 text-white w-full bg-cover bg-center relative rounded-xl p-4 overflow-hidden"
	style="background-image: url({banner});"
>
	<div class="absolute top-0 left-0 w-full h-full bg-black opacity-40 rounded-xl" />
	<div class="w-full h-full flex flex-col md:flex-row gap-2">
		<div class="z-[1] flex gap-x-2 items-start md:items-center w-full md:w-2/3">
			<a href={plexDebridItem.imdb_link} target="_blank" rel="noopener noreferrer">
				<img
					alt="test"
					src={poster}
					on:error={() => (poster = fallback)}
					class=" w-[4.5rem] min-w-[4.5rem] h-24 rounded-md hover:scale-105 transition-all ease-in-out duration-300"
				/>
			</a>
			<div class="flex flex-col">
				<p class="text-xl font-semibold md:text-ellipsis md:line-clamp-1">{plexDebridItem.title}</p>
				<p>{plexDebridItem.aired_at}</p>
			</div>
		</div>
		<div class="z-[1] flex flex-col items-start w-full md:w-1/2">
			<div class="flex gap-2 items-center">
				<p class="text-lg font-semibold">Status</p>
				<Badge class="{itemState.bg} text-black tracking-wider hover:text-white dark:hover:text-black">
					{itemState.text}
				</Badge>
			</div>
		</div>
	</div>
</div>

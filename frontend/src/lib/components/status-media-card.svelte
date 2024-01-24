<script lang="ts">
	import type { IcebergItem, StatusInterface } from '$lib/types';
	import { formatWords, formatDate } from '$lib/helpers';
	import { Badge } from '$lib/components/ui/badge';

	export let plexDebridItem: IcebergItem;
	export let itemState: StatusInterface;

	let fallback = 'https://via.placeholder.com/198x228.png?text=No+thumbnail';
	let poster = `https://images.metahub.space/poster/small/${plexDebridItem.imdb_id}/img`;
	let banner = `https://images.metahub.space/background/medium/${plexDebridItem.imdb_id}/img`;

	// TODO: Use item ID to show more data
	// TODO: Make use of type
</script>

<div
	class="flex flex-col md:flex-row md:justify-between gap-2 md:gap-0 text-white w-full bg-cover bg-center relative rounded-xl p-4 overflow-hidden border"
	style="background-image: url({banner});"
>
	<div class="absolute top-0 left-0 w-full h-full bg-slate-900 opacity-50 rounded-xl" />
	<div class="w-full h-full flex flex-col md:flex-row gap-2">
		<div
			class="z-[1] flex gap-x-2 items-start md:items-center w-full md:w-2/3 lg:w-3/4 xl:w-4/5 2xl:w-5/6"
		>
			<a href={plexDebridItem.imdb_link} target="_blank" rel="noopener noreferrer">
				<img
					alt="test"
					src={poster}
					on:error={() => (poster = fallback)}
					class=" w-[4.5rem] min-w-[4.5rem] h-24 rounded-md hover:scale-105 transition-all ease-in-out duration-300"
				/>
			</a>
			<div class="flex flex-col">
				<p class="text-lg lg:text-xl font-semibold md:text-ellipsis md:line-clamp-1">
					{plexDebridItem.title}
				</p>
				<p class="text-sm">Aired {formatDate(plexDebridItem.aired_at, 'short')}</p>
				<div class="flex flex-wrap gap-1 items-center mt-1 text-xs">
					{#each plexDebridItem.genres as genre}
						<Badge variant="secondary">
							{formatWords(genre)}
						</Badge>
					{/each}
				</div>
			</div>
		</div>
		<div class="z-[1] flex flex-col items-start w-full md:w-1/3 lg:w-1/4 xl:w-1/5 2xl:w-1/6">
			<div class="flex gap-2 items-center">
				<p class="text-base font-semibold">Status</p>
				<Badge class="{itemState.bg} tracking-wider text-black text-xs">
					{itemState.text ?? formatWords(plexDebridItem.state)}
				</Badge>
			</div>
			<div class="flex gap-2 items-center">
				<p class="text-base font-semibold">Requested</p>
				<p class="text-sm">{formatDate(plexDebridItem.requested_at, 'long', true)}</p>
			</div>
			<div class="flex gap-2 items-center">
				<p class="text-base font-semibold">Requested by</p>
				<p class="text-sm">{plexDebridItem.requested_by}</p>
			</div>
		</div>
	</div>
</div>

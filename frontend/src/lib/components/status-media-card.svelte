<script lang="ts">
	import type { PlexDebridItem } from '$lib/types';

	export let plexDebridItem: PlexDebridItem;

	let fallback = 'https://via.placeholder.com/198x228.png?text=No+thumbnail';
	let poster = `https://images.metahub.space/poster/small/${plexDebridItem.imdb_id}/img`;
</script>

<div
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
</div>

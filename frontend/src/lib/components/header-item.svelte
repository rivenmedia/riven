<script lang="ts">
	import { page } from '$app/stores';
	import type { NavItem } from '$lib/types';

	export let navItem: NavItem;
</script>

{#if $page.url.pathname === navItem.path}
	<a href={navItem.path}>
		<div
			class="relative text-xl hover:text-gray-700 dark:hover:text-gray-200 after:absolute after:bg-gray-800 dark:after:bg-gray-200 after:bottom-0 after:left-0 after:h-[2px] after:w-full after:origin-bottom-left after:scale-x-100 hover:after:origin-bottom-right hover:after:scale-x-0 after:transition-transform after:ease-in-out after:duration-300"
		>
			{navItem.name}
		</div>
	</a>
{:else}
	<a href={navItem.path}>
		<div
			class="relative text-xl hover:text-gray-700 dark:hover:text-gray-200 after:absolute after:bg-gray-800 dark:after:bg-gray-200 after:bottom-0 after:left-0 after:h-[2px] after:w-full after:origin-bottom-right after:scale-x-0 hover:after:origin-bottom-left hover:after:scale-x-100 after:transition-transform after:ease-in-out after:duration-300"
		>
			{navItem.name}
		</div>
	</a>
{/if}

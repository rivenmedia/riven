<script lang="ts">
    import type { PageData } from './$types';
    import { writable } from 'svelte/store';
    import { page } from '$app/stores';
    import Header from '$lib/components/header.svelte';
	import { SofaIcon } from 'lucide-svelte';
    
    export let data: PageData;

    $: pageSize = writable(Number($page.url.searchParams.get('limit') || 10));
    $: currentPage = writable(Number($page.url.searchParams.get('page') || 1));
    $: totalDataItems = writable(Number($page.data.items.total));
</script>

<Header />

<p>Soon™</p>
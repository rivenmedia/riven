<script lang="ts">
	import { ModeWatcher } from 'mode-watcher';
	import { Toaster } from '$lib/components/ui/sonner';
	import '../app.css';

	import { afterNavigate, beforeNavigate } from '$app/navigation';
	import NProgress from 'nprogress';
	import Header from '$lib/components/header.svelte';

	import { page } from '$app/stores';
	import { setContext } from 'svelte';
	import { dev } from '$app/environment';

	setContext('formDebug', dev);

	beforeNavigate(() => {
		NProgress.start();
	});
	afterNavigate(() => {
		NProgress.done();
	});
	NProgress.configure({
		showSpinner: false
	});
</script>

<ModeWatcher track={true} />
<Toaster richColors closeButton />

<!-- <div class="flex h-full w-full flex-col overflow-x-hidden font-primary font-medium">
	{#if !$page.url.pathname.startsWith('/onboarding')}
		<Header />
	{/if}
	<slot />
</div> -->

<div class="bg-background font-primary font-medium">
	<!-- {#if !$page.url.pathname.startsWith('/onboarding')}
		<Header />
	{/if} -->

	<slot />
</div>

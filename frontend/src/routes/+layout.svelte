<script>
	import { ModeWatcher } from 'mode-watcher';
	import { Toaster } from 'svelte-sonner';
	import '../app.pcss';
	import Header from '$lib/components/header.svelte';

</script>

<ModeWatcher track={true} />
<Toaster richColors closeButton />

<div class="font-primary flex flex-col w-full h-full overflow-x-hidden">
	<Header />
	<slot />
</div>

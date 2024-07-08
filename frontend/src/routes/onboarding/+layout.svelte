<script lang="ts">
	import { writable, type Writable } from 'svelte/store';
	import { setContext } from 'svelte';

	const formProgress = writable(0);
	setContext('formProgress', formProgress);
</script>

<svelte:head>
	<title>Onboarding | Riven</title>
</svelte:head>

<slot />

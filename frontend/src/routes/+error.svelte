<script lang="ts">
	import { page } from '$app/stores';
</script>

<div class="flex flex-col items-center justify-center w-full h-full font-primary">
	<h1 class="text-4xl font-bold text-center">Something went wrong</h1>
	<p class="text-lg text-muted-foreground">Error code: {$page.status}</p>
	<p class="text-base text-muted-foreground">Error message: {$page.error?.message}</p>
</div>

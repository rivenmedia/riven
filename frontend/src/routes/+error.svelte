<script lang="ts">
	import { page } from '$app/stores';
</script>

<div class="flex h-full w-full flex-col items-center justify-center font-primary font-medium">
	<h1 class="text-center text-3xl font-bold">Something went wrong</h1>
	<p class="text-base text-muted-foreground">Error code: {$page.status}</p>
	<p class="text-sm text-muted-foreground">Error message: {$page.error?.message}</p>
</div>

<script lang="ts">
	export let data;
</script>

<div class="flex flex-col p-8 md:px-24 lg:px-32 gap-2">
	<h1 class="text-4xl font-bold">Settings</h1>

	<pre>{JSON.stringify(data, null, 2)}</pre>
</div>

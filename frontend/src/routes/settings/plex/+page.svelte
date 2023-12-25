<script lang="ts">
	import type { PageData } from './$types';
	import { superForm } from 'sveltekit-superforms/client';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Button } from '$lib/components/ui/button';
	import { Separator } from '$lib/components/ui/separator';
	import { toast } from 'svelte-sonner';
	import { Loader2 } from 'lucide-svelte';
	import { page } from '$app/stores';

	export let data: PageData;
	const { form, errors, message, enhance, constraints, delayed } = superForm(data.form);

	$: if ($message && $page.status === 200) {
		toast.success($message);
	} else if ($message) {
		toast.error($message);
	}
</script>

<div class="flex flex-col">
	<h2 class="text-2xl md:text-3xl font-semibold">Plex Settings</h2>
	<p class="text-base md:text-lg text-muted-foreground">Configure settings for Plex.</p>

	<form method="POST" class="flex flex-col my-4 gap-4" use:enhance>
		<div class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
			<Label
				class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
				for="user">User</Label
			>
			<Input
				class="text-sm md:text-base"
				type="text"
				id="user"
				name="user"
				bind:value={$form.user}
				{...$constraints.user}
			/>
		</div>
		{#if $errors.user}
			<small class="text-sm md:text-base text-red-500">{$errors.user}</small>
		{/if}

		<div class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
			<Label
				class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
				for="token">Token</Label
			>
			<Input
				class="text-sm md:text-base"
				type="text"
				id="token"
				name="token"
				bind:value={$form.token}
				{...$constraints.token}
			/>
		</div>
		{#if $errors.token}
			<small class="text-sm md:text-base text-red-500">{$errors.token}</small>
		{/if}

		<div class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
			<Label
				class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
				for="url">Server URL</Label
			>
			<Input
				class="text-sm md:text-base"
				type="text"
				id="url"
				name="url"
				bind:value={$form.url}
				{...$constraints.url}
			/>
		</div>
		{#if $errors.url}
			<small class="text-sm md:text-base text-red-500">{$errors.url}</small>
		{/if}

		<div class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
			<Label
				class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
				for="watchlist">Watchlist RSS</Label
			>
			<Input
				class="text-sm md:text-base"
				type="text"
				id="watchlist"
				name="watchlist"
				bind:value={$form.watchlist}
				{...$constraints.watchlist}
			/>
		</div>
		{#if $errors.watchlist}
			<small class="text-sm md:text-base text-red-500">{$errors.watchlist}</small>
		{/if}

		<Separator class=" mt-4" />
		<div class="flex w-full justify-end">
			<Button disabled={$delayed} type="submit" size="sm" class="w-full md:max-w-max">
				{#if $delayed}
					<Loader2 class="w-4 h-4 animate-spin mr-2" />
				{/if}
				Save changes
			</Button>
		</div>
	</form>
</div>

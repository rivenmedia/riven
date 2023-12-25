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
	import clsx from 'clsx';

	export let data: PageData;
	const { form, errors, message, enhance, constraints, delayed } = superForm(data.form);

	$: if ($message && $page.status === 200) {
		toast.success($message);
	} else if ($message) {
		toast.error($message);
	}
</script>

<div class="flex flex-col">
	<h2 class="text-2xl md:text-3xl font-semibold">General Settings</h2>
	<p class="text-base md:text-lg text-muted-foreground">
		Configure global and default settings for Iceberg.
	</p>

	<form method="POST" class="flex flex-col my-4 gap-4" use:enhance>
		<div class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
			<Label
				class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
				for="host_mount">Host Mount</Label
			>
			<Input
				class="text-sm md:text-base"
				type="text"
				id="host_mount"
				name="host_mount"
				bind:value={$form.host_mount}
				{...$constraints.host_mount}
			/>
		</div>
		{#if $errors.host_mount}
			<small class="text-sm md:text-base text-red-500">{$errors.host_mount}</small>
		{/if}

		<div class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
			<Label
				class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
				for="container_mount">Container Mount</Label
			>
			<Input
				class="text-sm md:text-base"
				type="text"
				id="container_mount"
				name="container_mount"
				bind:value={$form.container_mount}
				{...$constraints.container_mount}
			/>
		</div>
		{#if $errors.container_mount}
			<p class="text-sm md:text-base text-red-500">{$errors.container_mount}</p>
		{/if}

		<div class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
			<Label
				class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
				for="realdebrid_api_key">RealDebrid API Key</Label
			>
			<Input
				class={clsx('transition-all duration-300 text-sm md:text-base', {
					'blur-sm hover:blur-none focus:blur-none': $form.realdebrid_api_key.length > 0
				})}
				type="text"
				id="realdebrid_api_key"
				name="realdebrid_api_key"
				bind:value={$form.realdebrid_api_key}
				{...$constraints.realdebrid_api_key}
			/>
		</div>
		{#if $errors.realdebrid_api_key}
			<p class="text-sm md:text-base text-red-500">{$errors.realdebrid_api_key}</p>
		{/if}

		<div class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
			<Label
				class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
				for="torrentio_filter">Torrentio Filter</Label
			>
			<Input
				class="text-sm md:text-base"
				type="text"
				id="torrentio_filter"
				name="torrentio_filter"
				bind:value={$form.torrentio_filter}
				{...$constraints.torrentio_filter}
			/>
		</div>
		{#if $errors.torrentio_filter}
			<p class="text-sm md:text-base text-red-500">{$errors.torrentio_filter}</p>
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

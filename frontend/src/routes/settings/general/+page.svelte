<script lang="ts">
	import type { PageData } from './$types';
	import { slide } from 'svelte/transition';
	import { superForm } from 'sveltekit-superforms/client';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Button } from '$lib/components/ui/button';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import { Separator } from '$lib/components/ui/separator';
	import { toast } from 'svelte-sonner';
	import { Loader2 } from 'lucide-svelte';
	import { page } from '$app/stores';
	import clsx from 'clsx';
	import SuperDebug from 'sveltekit-superforms/client/SuperDebug.svelte';

	export let data: PageData;
	const generalForm = superForm(data.form);
	const { form, errors, message, enhance, constraints, delayed } = generalForm;

	$: if ($message && $page.status === 200) {
		toast.success($message);
	} else if ($message) {
		toast.error($message);
	}
</script>

<SuperDebug data={$form} />

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
				spellcheck="false"
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
				spellcheck="false"
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
				spellcheck="false"
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

		<div class="flex flex-col md:flex-row items-start max-w-6xl gap-2">
			<Label class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
				>Scrapers Enabled</Label
			>
			<div class="flex flex-wrap gap-4">
				<div class="flex flex-wrap items-center gap-2">
					<Checkbox
						class="text-sm md:text-base"
						id="torrentio_enabled"
						name="torrentio_enabled"
						bind:checked={$form.torrentio_enabled}
						{...$constraints.torrentio_enabled}
					/>
					<Label class="text-sm md:text-base" for="torrentio_enabled">Torrentio</Label>
				</div>
				<div class="flex flex-wrap items-center gap-2">
					<Checkbox
						class="text-sm md:text-base"
						id="orionoid_enabled"
						name="orionoid_enabled"
						bind:checked={$form.orionoid_enabled}
						{...$constraints.orionoid_enabled}
					/>
					<Label class="text-sm md:text-base" for="orionoid_enabled">Orionoid</Label>
				</div>
				<div class="flex flex-wrap items-center gap-2">
					<Checkbox
						class="text-sm md:text-base"
						id="jackett_enabled"
						name="jackett_enabled"
						bind:checked={$form.jackett_enabled}
						{...$constraints.jackett_enabled}
					/>
					<Label class="text-sm md:text-base" for="jackett_enabled">Jackett</Label>
				</div>
			</div>
		</div>
		{#if $form.torrentio_enabled}
			<div transition:slide class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
				<Label
					class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
					for="torrentio_filter">Torrentio Filter</Label
				>
				<Input
					spellcheck="false"
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
		{/if}

		{#if $form.orionoid_enabled}
			<div transition:slide class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
				<Label
					class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
					for="orionoid_api_key">Orionoid API Key</Label
				>
				<Input
					spellcheck="false"
					class={clsx('transition-all duration-300 text-sm md:text-base', {
						'blur-sm hover:blur-none focus:blur-none': $form.orionoid_api_key.length > 0
					})}
					type="text"
					id="orionoid_api_key"
					name="orionoid_api_key"
					bind:value={$form.orionoid_api_key}
					{...$constraints.orionoid_api_key}
				/>
			</div>
		{/if}

		{#if $form.jackett_enabled}
			<div transition:slide class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
				<Label
					class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
					for="jackett_api_key">Jackett API Key</Label
				>
				<Input
					spellcheck="false"
					class={clsx('transition-all duration-300 text-sm md:text-base', {
						'blur-sm hover:blur-none focus:blur-none': $form.jackett_api_key.length > 0
					})}
					type="text"
					id="jackett_api_key"
					name="jackett_api_key"
					bind:value={$form.jackett_api_key}
					{...$constraints.jackett_api_key}
				/>
			</div>

			<div transition:slide class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
				<Label
					class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
					for="jackett_url">Jackett URL</Label
				>
				<Input
					spellcheck="false"
					class="text-sm md:text-base"
					type="text"
					id="jackett_url"
					name="jackett_url"
					bind:value={$form.jackett_url}
					{...$constraints.jackett_url}
				/>

				{#if $errors.jackett_url}
					<p class="text-sm md:text-base text-red-500">{$errors.jackett_url}</p>
				{/if}
			</div>
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

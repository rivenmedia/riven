<script lang="ts">
	import type { PageData } from './$types';
	import { invalidateAll } from '$app/navigation';
	import { superForm, arrayProxy } from 'sveltekit-superforms/client';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Button } from '$lib/components/ui/button';
	import { Separator } from '$lib/components/ui/separator';
	import { toast } from 'svelte-sonner';
	import { Loader2 } from 'lucide-svelte';
	import { page } from '$app/stores';
	import SuperDebug from 'sveltekit-superforms/client/SuperDebug.svelte';
	import clsx from 'clsx';

	export let data: PageData;
	const contentForm = superForm(data.form);
	const { form, errors, message, enhance, constraints, delayed } = contentForm;
	const { values: mdblistListsValues, errors: mdblistListsErrors } = arrayProxy(
		contentForm,
		'mdblist_lists'
	);

	$: if ($message && $page.status === 200) {
		toast.success($message);
	} else if ($message) {
		toast.error($message);
	}

	let current_add_list = '';
	function addToMdblistLists(event: SubmitEvent): void {
		event.preventDefault();
		// see if current_add_list is already in the list
		if ($mdblistListsValues.includes(current_add_list)) {
			current_add_list = '';
			toast.error('List already exists');
			return;
		}
		// see if current_add_list can be converted to a number
		if (isNaN(Number(current_add_list))) {
			current_add_list = '';
			toast.error('List must be a number');
			return;
		}
		$mdblistListsValues = [...$mdblistListsValues.filter((item) => item !== ''), current_add_list];
		current_add_list = '';
	}
</script>

<svelte:head>
	<title>Content | Settings</title>
</svelte:head>

<SuperDebug data={$form} />

<div class="flex flex-col">
	<h2 class="text-2xl md:text-3xl font-semibold">Content Settings</h2>
	<p class="text-base md:text-lg text-muted-foreground">Configure settings for content services.</p>

	<form method="POST" class="flex flex-col my-4 gap-4" use:enhance>
		<div class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
			<Label
				class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
				for="overseerr_url">Overseerr URL</Label
			>
			<Input
				class="text-sm md:text-base"
				type="text"
				id="overseerr_url"
				name="overseerr_url"
				bind:value={$form.overseerr_url}
				{...$constraints.overseerr_url}
			/>
		</div>
		{#if $errors.overseerr_url}
			<small class="text-sm md:text-base text-red-500">{$errors.overseerr_url}</small>
		{/if}

		<div class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
			<Label
				class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
				for="overseerr_api_key">Overseerr API Key</Label
			>
			<Input
				class={clsx('transition-all duration-300 text-sm md:text-base', {
					'blur-sm hover:blur-none focus:blur-none': $form.overseerr_api_key.length > 0
				})}
				type="text"
				id="overseerr_api_key"
				name="overseerr_api_key"
				bind:value={$form.overseerr_api_key}
				{...$constraints.overseerr_api_key}
			/>
		</div>
		{#if $errors.overseerr_api_key}
			<small class="text-sm md:text-base text-red-500">{$errors.overseerr_api_key}</small>
		{/if}

		<div class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
			<Label
				class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
				for="mdblist_api_key">Mdblist API Key</Label
			>
			<Input
				class={clsx('transition-all duration-300 text-sm md:text-base', {
					'blur-sm hover:blur-none focus:blur-none': $form.mdblist_api_key.length > 0
				})}
				type="text"
				id="mdblist_api_key"
				name="mdblist_api_key"
				bind:value={$form.mdblist_api_key}
				{...$constraints.mdblist_api_key}
			/>
		</div>
		{#if $errors.mdblist_api_key}
			<small class="text-sm md:text-base text-red-500">{$errors.mdblist_api_key}</small>
		{/if}

		<div class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
			<Label
				class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
				for="mdblist_update_interval">Mdblist Update Interval</Label
			>
			<Input
				class="text-sm md:text-base"
				type="number"
				id="mdblist_update_interval"
				name="mdblist_update_interval"
				bind:value={$form.mdblist_update_interval}
				{...$constraints.mdblist_update_interval}
			/>
		</div>
		{#if $errors.mdblist_update_interval}
			<small class="text-sm md:text-base text-red-500">{$errors.mdblist_update_interval}</small>
		{/if}

		<pre>{JSON.stringify($mdblistListsValues)}</pre>

		<!--h-0 overflow-hidden instead of hidden because it prevents `required` from operating-->
		<div class="h-0 overflow-hidden">
			<select
				multiple
				id="mdblist_lists"
				name="mdblist_lists"
				bind:value={$mdblistListsValues}
				tabindex="-1"
				{...$constraints.mdblist_lists}
			>
				{#each $mdblistListsValues as list}
					<option value={list}>{list}</option>
				{/each}
			</select>
		</div>

		{#if $mdblistListsErrors}
			<small class="text-sm md:text-base text-red-500">{$mdblistListsErrors}</small>
		{/if}

		<form on:submit={addToMdblistLists}>
			<input type="text" bind:value={current_add_list} />
		</form>

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

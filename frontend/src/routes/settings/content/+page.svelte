<script lang="ts">
	import type { PageData } from './$types';
	import { superForm, arrayProxy } from 'sveltekit-superforms/client';
	import { fly } from 'svelte/transition';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Button } from '$lib/components/ui/button';
	import { Separator } from '$lib/components/ui/separator';
	import { toast } from 'svelte-sonner';
	import { Loader2, X } from 'lucide-svelte';
	import { page } from '$app/stores';
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
		if ($mdblistListsValues.includes(current_add_list)) {
			current_add_list = '';
			toast.error('List already exists');
			return;
		}
		if (isNaN(Number(current_add_list))) {
			current_add_list = '';
			toast.error('List must be a number');
			return;
		}
		if (Number(current_add_list) <= 0) {
			current_add_list = '';
			toast.error('List must be a positive number (> 0)');
			return;
		}
		$mdblistListsValues = [...$mdblistListsValues.filter((item) => item !== ''), current_add_list];
		current_add_list = '';
	}

	function removeFromMdblistLists(list: string): void {
		$mdblistListsValues = $mdblistListsValues.filter((item) => item !== list);
		if ($mdblistListsValues.length === 0) {
			$mdblistListsValues = [''];
		}
	}
</script>

<svelte:head>
	<title>Content | Settings</title>
</svelte:head>

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

		<div class="flex flex-col md:flex-row items-start max-w-6xl">
			<Label
				class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
				for="mdblist_lists">Mdblist Lists</Label
			>
			<form on:submit={addToMdblistLists} class="w-full flex flex-col gap-4 items-start">
				<Input
					placeholder="Enter list numbers one at a time"
					class="text-sm md:text-base"
					type="number"
					bind:value={current_add_list}
				/>
				<div class="flex items-center w-full flex-wrap gap-2">
					{#each $mdblistListsValues.filter((list) => list !== '') as list (list)}
						<button
							type="button"
							in:fly={{ y: 10, duration: 200 }}
							out:fly={{ y: -10, duration: 200 }}
							class="flex items-center gap-2 py-1 px-6 text-sm bg-slate-200 dark:bg-slate-800 rounded-md"
							on:click={() => removeFromMdblistLists(list)}
						>
							<p>{list}</p>
							<X class="w-4 h-4 text-red-500" />
						</button>
					{/each}
				</div>
			</form>
		</div>

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

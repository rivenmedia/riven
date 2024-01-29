<script lang="ts">
	import { slide, fly } from 'svelte/transition';
	import { arrayProxy, superForm } from 'sveltekit-superforms/client';
	import { Button } from '$lib/components/ui/button';
	import { Separator } from '$lib/components/ui/separator';
	import { toast } from 'svelte-sonner';
	import { Loader2, X } from 'lucide-svelte';
	import { page } from '$app/stores';
	import clsx from 'clsx';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import * as Form from '$lib/components/ui/form';
	import { contentSettingsSchema, type ContentSettingsSchema } from '$lib/forms/helpers';
	import { getContext } from 'svelte';
	import type { SuperValidated } from 'sveltekit-superforms';

	let formDebug: boolean = getContext('formDebug');

	export let data: SuperValidated<ContentSettingsSchema>;
	const contentForm = superForm(data);
	const { form, message, delayed, errors } = contentForm;

	const { values: mdblistListsValues, errors: mdblistListsErrors } = arrayProxy(
		contentForm,
		'mdblist_lists'
	);

	const { values: listrrMovieListsValues, errors: listrrMovieListsErrors } = arrayProxy(
		contentForm,
		'listrr_movie_lists'
	);

	const { values: listrrShowListsValues, errors: listrrShowListsErrors } = arrayProxy(
		contentForm,
		'listrr_show_lists'
	);

	$: if ($message && $page.status === 200) {
		toast.success($message);
	} else if ($message) {
		toast.error($message);
	}

	let current_mdb_add_list = '';
	let current_listrr_movie_add_list = '';
	let current_listrr_show_add_list = '';

	// TODO: make this into a tag component
	function addToList(event: any, type: string): void {
		event.preventDefault();
		if (type === 'mdblist') {
			if (isNaN(Number(current_mdb_add_list))) {
				current_mdb_add_list = '';
				toast.error('List must be a number');
				return;
			}
			if (Number(current_mdb_add_list) <= 0) {
				current_mdb_add_list = '';
				toast.error('List must be a positive number (> 0)');
				return;
			}
			if ($mdblistListsValues.includes(current_mdb_add_list)) {
				current_mdb_add_list = '';
				toast.error('List already exists');
				return;
			}
			$mdblistListsValues = [
				...$mdblistListsValues.filter((item) => item !== ''),
				current_mdb_add_list
			];
			current_mdb_add_list = '';
		} else if (type === 'listrr_movie') {
			if ($listrrMovieListsValues.includes(current_listrr_movie_add_list)) {
				current_listrr_movie_add_list = '';
				toast.error('List already exists');
				return;
			}
			$listrrMovieListsValues = [
				...$listrrMovieListsValues.filter((item) => item !== ''),
				current_listrr_movie_add_list
			];
			current_listrr_movie_add_list = '';
		} else if (type === 'listrr_show') {
			if ($listrrShowListsValues.includes(current_listrr_show_add_list)) {
				current_listrr_show_add_list = '';
				toast.error('List already exists');
				return;
			}
			$listrrShowListsValues = [
				...$listrrShowListsValues.filter((item) => item !== ''),
				current_listrr_show_add_list
			];
			current_listrr_show_add_list = '';
		}
	}

	function removeFromList(list: string, type: string): void {
		if (type === 'mdblist') {
			$mdblistListsValues = $mdblistListsValues.filter((item) => item !== list);
			if ($mdblistListsValues.length === 0) {
				$mdblistListsValues = [''];
			}
		} else if (type === 'listrr_movie') {
			$listrrMovieListsValues = $listrrMovieListsValues.filter((item) => item !== list);
			if ($listrrMovieListsValues.length === 0) {
				$listrrMovieListsValues = [''];
			}
		} else if (type === 'listrr_show') {
			$listrrShowListsValues = $listrrShowListsValues.filter((item) => item !== list);
			if ($listrrShowListsValues.length === 0) {
				$listrrShowListsValues = [''];
			}
		}
	}

	export let actionUrl: string = '?/default';
</script>

<Form.Root
	action={actionUrl}
	schema={contentSettingsSchema}
	controlled
	form={contentForm}
	let:config
	debug={formDebug}
>
	<div class="flex flex-col my-4 gap-4">
		<div class="flex flex-col md:flex-row items-start md:items-center max-w-6xl gap-2">
			<p class="font-semibold w-48 min-w-48 text-muted-foreground">Content Providers</p>
			<div class="flex flex-wrap gap-4">
				<Form.Field {config} name="overseerr_enabled">
					<div class="flex flex-wrap items-center gap-2">
						<Form.Checkbox />
						<Form.Label>Overseerr</Form.Label>
					</div>
				</Form.Field>

				<Form.Field {config} name="mdblist_enabled">
					<div class="flex flex-wrap items-center gap-2">
						<Form.Checkbox />
						<Form.Label>Mdblist</Form.Label>
					</div>
				</Form.Field>

				<Form.Field {config} name="plex_watchlist_enabled">
					<div class="flex flex-wrap items-center gap-2">
						<Form.Checkbox />
						<Form.Label>Plex Watchlists</Form.Label>
					</div>
				</Form.Field>

				<Form.Field {config} name="listrr_enabled">
					<div class="flex flex-wrap items-center gap-2">
						<Form.Checkbox />
						<Form.Label>Listrr</Form.Label>
					</div>
				</Form.Field>
			</div>
		</div>

		{#if $form.overseerr_enabled}
			<div transition:slide>
				<Form.Field {config} name="overseerr_url">
					<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
						<Form.Label class="font-semibold w-48 min-w-48 text-muted-foreground">
							Overseerr URL
						</Form.Label>
						<Form.Input spellcheck="false" />
					</Form.Item>
					{#if $errors.overseerr_url}
						<Form.Validation class="text-sm text-red-500" />
					{/if}
				</Form.Field>
			</div>

			<div transition:slide>
				<Form.Field {config} name="overseerr_api_key">
					<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
						<Form.Label class="font-semibold w-48 min-w-48 text-muted-foreground">
							Overseerr API Key
						</Form.Label>
						<Form.Input
							class={clsx('transition-all duration-300', {
								'blur-sm hover:blur-none focus:blur-none': $form.overseerr_api_key.length > 0
							})}
							spellcheck="false"
						/>
					</Form.Item>
					{#if $errors.overseerr_api_key}
						<Form.Validation class="text-sm text-red-500" />
					{/if}
				</Form.Field>
			</div>
		{/if}

		{#if $form.plex_watchlist_enabled}
			<div transition:slide>
				<Form.Field {config} name="plex_watchlist_rss">
					<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
						<Form.Label class="font-semibold w-48 min-w-48 text-muted-foreground">
							Plex RSS URL (Optional)
						</Form.Label>
						<Form.Input spellcheck="false" />
					</Form.Item>
					{#if $errors.plex_watchlist_rss}
						<Form.Validation class="text-sm text-red-500" />
					{/if}
				</Form.Field>
			</div>

			<div transition:slide>
				<Form.Field {config} name="plex_watchlist_update_interval">
					<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
						<Form.Label class="font-semibold w-48 min-w-48 text-muted-foreground">
							Plex RSS Update Interval
						</Form.Label>
						<Form.Input type="number" spellcheck="false" />
					</Form.Item>
					{#if $errors.plex_watchlist_update_interval}
						<Form.Validation class="text-sm text-red-500" />
					{/if}
				</Form.Field>
			</div>
		{/if}

		<!--h-0 overflow-hidden instead of hidden because it prevents `required` from operating, outside of if to persist-->
		<div class="h-0 overflow-hidden">
			<select
				multiple
				id="mdblist_lists"
				name="mdblist_lists"
				bind:value={$mdblistListsValues}
				tabindex="-1"
			>
				{#each $mdblistListsValues as list}
					<option value={list}>{list}</option>
				{/each}
			</select>
		</div>

		{#if $form.mdblist_enabled}
			<div transition:slide>
				<Form.Field {config} name="mdblist_api_key">
					<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
						<Form.Label class="font-semibold w-48 min-w-48 text-muted-foreground">
							Mdblist API Key
						</Form.Label>
						<Form.Input
							class={clsx('transition-all duration-300', {
								'blur-sm hover:blur-none focus:blur-none': $form.mdblist_api_key.length > 0
							})}
							spellcheck="false"
						/>
					</Form.Item>
					{#if $errors.mdblist_api_key}
						<Form.Validation class="text-sm text-red-500" />
					{/if}
				</Form.Field>
			</div>

			<div transition:slide>
				<Form.Field {config} name="mdblist_update_interval">
					<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
						<Form.Label class="font-semibold w-48 min-w-48 text-muted-foreground">
							Mdblist Update Interval
						</Form.Label>
						<Form.Input type="number" spellcheck="false" />
					</Form.Item>
					{#if $errors.mdblist_update_interval}
						<Form.Validation class="text-sm text-red-500" />
					{/if}
				</Form.Field>
			</div>

			{#if $mdblistListsErrors}
				<small class="text-sm text-red-500">{$mdblistListsErrors}</small>
			{/if}

			<div transition:slide class="flex flex-col md:flex-row items-start max-w-6xl gap-2">
				<Label class="font-semibold w-48 min-w-48 text-muted-foreground" for="mdblist_lists"
					>Mdblist Lists</Label
				>
				<form
					on:submit={() => {
						addToList(event, 'mdblist');
					}}
					class="w-full flex flex-col gap-4 items-start"
				>
					<Input
						placeholder="Enter list numbers one at a time"
						type="number"
						bind:value={current_mdb_add_list}
					/>
					<div class="flex items-center w-full flex-wrap gap-2">
						{#each $mdblistListsValues.filter((list) => list !== '') as list (list)}
							<button
								type="button"
								in:fly={{ y: 10, duration: 200 }}
								out:fly={{ y: -10, duration: 200 }}
								class="flex items-center gap-2 py-1 px-6 text-sm bg-slate-200 dark:bg-slate-800 rounded-md"
								on:click={() => removeFromList(list, 'mdblist')}
							>
								<p>{list}</p>
								<X class="w-4 h-4 text-red-500" />
							</button>
						{/each}
					</div>
				</form>
			</div>
		{/if}

		<div class="h-0 overflow-hidden">
			<select
				multiple
				id="listrr_movie_lists"
				name="listrr_movie_lists"
				bind:value={$listrrMovieListsValues}
				tabindex="-1"
			>
				{#each $listrrMovieListsValues as list}
					<option value={list}>{list}</option>
				{/each}
			</select>
		</div>

		<div class="h-0 overflow-hidden">
			<select
				multiple
				id="listrr_show_lists"
				name="listrr_show_lists"
				bind:value={$listrrShowListsValues}
				tabindex="-1"
			>
				{#each $listrrShowListsValues as list}
					<option value={list}>{list}</option>
				{/each}
			</select>
		</div>

		{#if $form.listrr_enabled}
			<div transition:slide>
				<Form.Field {config} name="listrr_api_key">
					<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
						<Form.Label class="font-semibold w-48 min-w-48 text-muted-foreground">
							Listrr API Key
						</Form.Label>
						<Form.Input
							class={clsx('transition-all duration-300', {
								'blur-sm hover:blur-none focus:blur-none': $form.listrr_api_key.length > 0
							})}
							spellcheck="false"
						/>
					</Form.Item>
					{#if $errors.listrr_api_key}
						<Form.Validation class="text-sm text-red-500" />
					{/if}
				</Form.Field>
			</div>

			<div transition:slide>
				<Form.Field {config} name="listrr_update_interval">
					<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
						<Form.Label class="font-semibold w-48 min-w-48 text-muted-foreground">
							Listrr Update Interval
						</Form.Label>
						<Form.Input type="number" spellcheck="false" />
					</Form.Item>
					{#if $errors.listrr_update_interval}
						<Form.Validation class="text-sm text-red-500" />
					{/if}
				</Form.Field>
			</div>

			{#if $listrrMovieListsErrors}
				<small class="text-sm text-red-500">{$listrrMovieListsErrors}</small>
			{/if}
			{#if $listrrShowListsErrors}
				<small class="text-sm text-red-500">{$listrrShowListsErrors}</small>
			{/if}

			<div transition:slide class="flex flex-col md:flex-row items-start max-w-6xl gap-2">
				<Label class="font-semibold w-48 min-w-48 text-muted-foreground" for="listrr_movie_lists"
					>Listrr Movie Lists</Label
				>
				<form
					on:submit={() => {
						addToList(event, 'listrr_movie');
					}}
					class="w-full flex flex-col gap-4 items-start"
				>
					<Input
						placeholder="Enter list numbers one at a time"
						bind:value={current_listrr_movie_add_list}
					/>
					<div class="flex items-center w-full flex-wrap gap-2">
						{#each $listrrMovieListsValues.filter((list) => list !== '') as list (list)}
							<button
								type="button"
								in:fly={{ y: 10, duration: 200 }}
								out:fly={{ y: -10, duration: 200 }}
								class="flex items-center gap-2 py-1 px-6 text-sm bg-slate-200 dark:bg-slate-800 rounded-md"
								on:click={() => removeFromList(list, 'listrr_movie')}
							>
								<p>{list}</p>
								<X class="w-4 h-4 text-red-500" />
							</button>
						{/each}
					</div>
				</form>
			</div>

			<div transition:slide class="flex flex-col md:flex-row items-start max-w-6xl gap-2">
				<Label class="font-semibold w-48 min-w-48 text-muted-foreground" for="listrr_show_lists"
					>Listrr Show Lists</Label
				>
				<form
					on:submit={() => {
						addToList(event, 'listrr_show');
					}}
					class="w-full flex flex-col gap-4 items-start"
				>
					<Input
						placeholder="Enter list numbers one at a time"
						bind:value={current_listrr_show_add_list}
					/>
					<div class="flex items-center w-full flex-wrap gap-2">
						{#each $listrrShowListsValues.filter((list) => list !== '') as list (list)}
							<button
								type="button"
								in:fly={{ y: 10, duration: 200 }}
								out:fly={{ y: -10, duration: 200 }}
								class="flex items-center gap-2 py-1 px-6 text-sm bg-slate-200 dark:bg-slate-800 rounded-md"
								on:click={() => removeFromList(list, 'listrr_show')}
							>
								<p>{list}</p>
								<X class="w-4 h-4 text-red-500" />
							</button>
						{/each}
					</div>
				</form>
			</div>
		{/if}

		<Separator class=" mt-4" />
		<div class="flex w-full justify-end">
			<Button
				disabled={$delayed}
				type="submit"
				size="sm"
				class="w-full md:max-w-max font-medium text-xs"
			>
				{#if $delayed}
					<Loader2 class="w-4 h-4 animate-spin mr-2" />
				{/if}
				Save changes
				<span class="ml-1" class:hidden={$page.url.pathname === '/settings/content'}
					>and continue</span
				>
			</Button>
		</div>
	</div>
</Form.Root>

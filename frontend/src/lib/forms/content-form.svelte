<script lang="ts">
	import { slide } from 'svelte/transition';
	import { arrayProxy, superForm } from 'sveltekit-superforms/client';
	import { Button } from '$lib/components/ui/button';
	import { Separator } from '$lib/components/ui/separator';
	import { toast } from 'svelte-sonner';
	import { Loader2 } from 'lucide-svelte';
	import { page } from '$app/stores';
	import * as Form from '$lib/components/ui/form';
	import { contentSettingsSchema, type ContentSettingsSchema } from '$lib/forms/helpers';
	import { getContext } from 'svelte';
	import type { SuperValidated } from 'sveltekit-superforms';
	import FormTextField from './components/form-text-field.svelte';
	import FormNumberField from './components/form-number-field.svelte';
	import FormGroupCheckboxField from './components/form-group-checkbox-field.svelte';
	import type { FormGroupCheckboxFieldType } from '$lib/types';
	import FormTagsInputField from './components/form-tags-input-field.svelte';

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

	export let actionUrl: string = '?/default';
	const contentProvidersFieldData: FormGroupCheckboxFieldType[] = [
		{
			field_name: 'overseerr_enabled',
			label_name: 'Overseerr'
		},
		{
			field_name: 'mdblist_enabled',
			label_name: 'Mdblist'
		},
		{
			field_name: 'plex_watchlist_enabled',
			label_name: 'Plex Watchlists'
		},
		{
			field_name: 'listrr_enabled',
			label_name: 'Listrr'
		}
	];
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
		<FormGroupCheckboxField
			{config}
			fieldTitle="Content Providers"
			fieldData={contentProvidersFieldData}
		/>

		{#if $form.overseerr_enabled}
			<div transition:slide>
				<FormTextField
					{config}
					fieldName="overseerr_url"
					labelName="Overseerr URL"
					errors={$errors.overseerr_url}
				/>
			</div>

			<div transition:slide>
				<FormTextField
					{config}
					fieldName="overseerr_api_key"
					isProtected={true}
					fieldValue={$form.overseerr_api_key}
					labelName="Overseerr API Key"
					errors={$errors.overseerr_api_key}
				/>
			</div>
		{/if}

		{#if $form.plex_watchlist_enabled}
			<div transition:slide>
				<FormTextField
					{config}
					fieldName="plex_watchlist_rss"
					fieldDescription="This is an optional field. Without it, adding to watchlists will still work."
					labelName="Plex RSS URL"
					errors={$errors.plex_watchlist_rss}
				/>
			</div>

			<div transition:slide>
				<FormNumberField
					{config}
					stepValue={undefined}
					fieldName="plex_watchlist_update_interval"
					labelName="Plex RSS Update Interval"
					errors={$errors.plex_watchlist_update_interval}
				/>
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
				<FormTextField
					{config}
					fieldName="mdblist_api_key"
					isProtected={true}
					fieldValue={$form.mdblist_api_key}
					labelName="Mdblist API Key"
					errors={$errors.mdblist_api_key}
				/>
			</div>

			<div transition:slide>
				<FormNumberField
					{config}
					stepValue={undefined}
					fieldName="mdblist_update_interval"
					labelName="Mdblist Update Interval"
					errors={$errors.mdblist_update_interval}
				/>
			</div>

			{#if $mdblistListsErrors}
				<small class="text-sm text-red-500">{$mdblistListsErrors}</small>
			{/if}

			<div transition:slide>
				<FormTagsInputField
					fieldName="mdblist_lists"
					labelName="Mdblist Lists"
					fieldValue={mdblistListsValues}
					numberValidate={true}
				/>
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
				<FormTextField
					{config}
					fieldName="listrr_api_key"
					isProtected={true}
					fieldValue={$form.listrr_api_key}
					labelName="Listrr API Key"
					errors={$errors.listrr_api_key}
				/>
			</div>

			<div transition:slide>
				<FormNumberField
					{config}
					stepValue={undefined}
					fieldName="listrr_update_interval"
					labelName="Listrr Update Interval"
					errors={$errors.listrr_update_interval}
				/>
			</div>

			{#if $listrrMovieListsErrors}
				<small class="text-sm text-red-500">{$listrrMovieListsErrors}</small>
			{/if}
			{#if $listrrShowListsErrors}
				<small class="text-sm text-red-500">{$listrrShowListsErrors}</small>
			{/if}

			<div transition:slide>
				<FormTagsInputField
					fieldName="listrr_movie_lists"
					labelName="Listrr Movie Lists"
					fieldValue={listrrMovieListsValues}
					numberValidate={false}
				/>
			</div>

			<div transition:slide>
				<FormTagsInputField
					fieldName="listrr_show_lists"
					labelName="Listrr Show Lists"
					fieldValue={listrrShowListsValues}
					numberValidate={false}
				/>
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

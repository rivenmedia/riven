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
	import FormCheckboxField from './components/form-checkbox-field.svelte';

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

	const { values: traktWatchlistValues, errors: traktWatchlistErrors } = arrayProxy(
		contentForm,
		'trakt_watchlist'
	);

	const { values: traktUserListsValues, errors: traktUserListsErrors } = arrayProxy(
		contentForm,
		'trakt_user_lists'
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
		},
		{
			field_name: 'trakt_enabled',
			label_name: 'Trakt'
		}
	];

	const traktFetchFieldData: FormGroupCheckboxFieldType[] = [
		{
			field_name: 'trakt_fetch_trending',
			label_name: 'Trending'
		},
		{
			field_name: 'trakt_fetch_popular',
			label_name: 'Popular'
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

			<div transition:slide>
				<FormNumberField
					{config}
					stepValue={undefined}
					fieldName="overseerr_update_interval"
					labelName="Overseerr Update Interval"
					errors={$errors.overseerr_update_interval}
				/>
			</div>

		<div transition:slide>
			<FormCheckboxField
					{config}
					fieldName="overseerr_use_webhook"
					labelName="Use Webhook"
					bind:fieldValue={$form.overseerr_use_webhook}
					errors={$errors.overseerr_use_webhook}
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

		<div class="h-0 overflow-hidden">
			<select
				multiple
				id="trakt_watchlist"
				name="trakt_watchlist"
				bind:value={$traktWatchlistValues}
				tabindex="-1"
			>
				{#each $traktWatchlistValues as list}
					<option value={list}>{list}</option>
				{/each}
			</select>
		</div>

		<div class="h-0 overflow-hidden">
			<select
				multiple
				id="trakt_user_lists"
				name="trakt_user_lists"
				bind:value={$traktUserListsValues}
				tabindex="-1"
			>
				{#each $traktUserListsValues as list}
					<option value={list}>{list}</option>
				{/each}
			</select>
		</div>

		{#if $form.trakt_enabled}
			<div transition:slide>
				<FormTextField
					{config}
					fieldName="trakt_api_key"
					isProtected={true}
					fieldValue={$form.trakt_api_key}
					labelName="Trakt API Key"
					errors={$errors.trakt_api_key}
				/>
			</div>

			<div transition:slide>
				<FormNumberField
					{config}
					stepValue={undefined}
					fieldName="trakt_update_interval"
					labelName="Trakt Update Interval"
					errors={$errors.trakt_update_interval}
				/>
			</div>

			{#if $traktWatchlistErrors}
				<small class="text-sm text-red-500">{$traktWatchlistErrors}</small>
			{/if}
			{#if $traktUserListsErrors}
				<small class="text-sm text-red-500">{$traktUserListsErrors}</small>
			{/if}

			<div transition:slide>
				<FormTagsInputField
					fieldName="trakt_watchlist"
					labelName="Trakt Watchlist"
					fieldValue={traktWatchlistValues}
					numberValidate={false}
				/>
			</div>

			<div transition:slide>
				<FormTagsInputField
					fieldName="trakt_user_lists"
					labelName="Trakt User Lists"
					fieldValue={traktUserListsValues}
					numberValidate={false}
				/>
			</div>

			<FormGroupCheckboxField {config} fieldTitle="Fetch Lists" fieldData={traktFetchFieldData} />

			{#if $form.trakt_fetch_trending}
				<div transition:slide>
					<FormNumberField
						{config}
						stepValue={1}
						fieldName="trakt_trending_count"
						labelName="Trending Count"
						errors={$errors.trakt_trending_count}
					/>
				</div>
			{/if}

			{#if $form.trakt_fetch_popular}
				<div transition:slide>
					<FormNumberField
						{config}
						stepValue={1}
						fieldName="trakt_popular_count"
						labelName="Popular Count"
						errors={$errors.trakt_popular_count}
					/>
				</div>
			{/if}
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

<script lang="ts">
	import { slide } from 'svelte/transition';
	import { page } from '$app/stores';
	import { getContext } from 'svelte';
	import SuperDebug from 'sveltekit-superforms';
	import { zodClient } from 'sveltekit-superforms/adapters';
	import { type SuperValidated, type Infer, superForm } from 'sveltekit-superforms';
	import * as Form from '$lib/components/ui/form';
	import { contentSettingsSchema, type ContentSettingsSchema } from '$lib/forms/helpers';
	import { toast } from 'svelte-sonner';
	import TextField from './components/text-field.svelte';
	import NumberField from './components/number-field.svelte';
	import CheckboxField from './components/checkbox-field.svelte';
	import GroupCheckboxField from './components/group-checkbox-field.svelte';
	import ArrayField from './components/array-field.svelte';
	import { Loader2, Trash2, Plus } from 'lucide-svelte';
	import { Separator } from '$lib/components/ui/separator';
	import { Input } from '$lib/components/ui/input';

	export let data: SuperValidated<Infer<ContentSettingsSchema>>;
	export let actionUrl: string = '?/default';

	const formDebug: boolean = getContext('formDebug');

	const form = superForm(data, {
		validators: zodClient(contentSettingsSchema)
	});

	const { form: formData, enhance, message, errors, delayed } = form;

	$: if ($message && $page.status === 200) {
		toast.success($message);
	} else if ($message) {
		toast.error($message);
	}

	function addField(name: string) {
		// @ts-ignore eslint-disable-next-line
		$formData[name] = [...$formData[name], ''];
	}

	function removeField(name: string, index: number) {
		// @ts-ignore eslint-disable-next-line
		$formData[name] = $formData[name].filter((_, i) => i !== index);
	}
</script>

<form method="POST" action={actionUrl} use:enhance class="my-8 flex flex-col gap-2">
	<!-- overseerr_enabled, mdblist_enabled, plex_watchlist_enabled, , listrr_enabled, trakt_enabled -->

	<GroupCheckboxField
		fieldTitle="Content Providers"
		fieldDescription="Enable the content providers you want to use"
	>
		<CheckboxField {form} name="overseerr_enabled" label="Overseerr" {formData} isForGroup={true} />
		<CheckboxField {form} name="mdblist_enabled" label="MDB List" {formData} isForGroup={true} />
		<CheckboxField
			{form}
			name="plex_watchlist_enabled"
			label="Plex Watchlist"
			{formData}
			isForGroup={true}
		/>
		<CheckboxField {form} name="listrr_enabled" label="Listrr" {formData} isForGroup={true} />
		<CheckboxField {form} name="trakt_enabled" label="Trakt" {formData} isForGroup={true} />
	</GroupCheckboxField>

	{#if $formData.overseerr_enabled}
		<div transition:slide>
			<TextField {form} name="overseerr_url" {formData} />
		</div>

		<div transition:slide>
			<TextField {form} name="overseerr_api_key" {formData} isProtected={true} />
		</div>

		<div transition:slide>
			<NumberField {form} name="overseerr_update_interval" {formData} stepValue={1} />
		</div>

		<div transition:slide>
			<CheckboxField {form} name="overseerr_use_webhook" {formData} />
		</div>
	{/if}

	{#if $formData.mdblist_enabled}
		<div transition:slide>
			<TextField {form} name="mdblist_api_key" {formData} isProtected={true} />
		</div>

		<div transition:slide>
			<ArrayField {form} name="mdblist_lists" {formData}>
				{#each $formData.mdblist_lists as _, i}
					<Form.ElementField {form} name="mdblist_lists[{i}]">
						<Form.Control let:attrs>
							<div class="flex items-center gap-2">
								<Input
									type="text"
									spellcheck="false"
									autocomplete="false"
									{...attrs}
									bind:value={$formData.mdblist_lists[i]}
								/>

								<div class="flex items-center gap-2">
									<Form.Button
										type="button"
										size="sm"
										variant="destructive"
										on:click={() => {
											removeField('mdblist_lists', i);
										}}
									>
										<Trash2 class="h-4 w-4" />
									</Form.Button>
								</div>
							</div>
						</Form.Control>
					</Form.ElementField>
				{/each}

				<div class="flex w-full items-center justify-between gap-2">
					<p class="text-muted-foreground text-sm">Add MDB Lists</p>
					<Form.Button
						type="button"
						size="sm"
						variant="outline"
						on:click={() => {
							addField('mdblist_lists');
						}}
					>
						<Plus class="h-4 w-4" />
					</Form.Button>
				</div>
			</ArrayField>
		</div>

		<div transition:slide>
			<NumberField {form} name="mdblist_update_interval" {formData} stepValue={1} />
		</div>
	{/if}

	{#if $formData.plex_watchlist_enabled}
		<div transition:slide>
			<ArrayField {form} name="plex_watchlist_rss" {formData}>
				{#each $formData.plex_watchlist_rss as _, i}
					<Form.ElementField {form} name="plex_watchlist_rss[{i}]">
						<Form.Control let:attrs>
							<div class="flex items-center gap-2">
								<Input
									type="text"
									spellcheck="false"
									autocomplete="false"
									{...attrs}
									bind:value={$formData.plex_watchlist_rss[i]}
								/>

								<div class="flex items-center gap-2">
									<Form.Button
										type="button"
										size="sm"
										variant="destructive"
										on:click={() => {
											removeField('plex_watchlist_rss', i);
										}}
									>
										<Trash2 class="h-4 w-4" />
									</Form.Button>
								</div>
							</div>
						</Form.Control>
					</Form.ElementField>
				{/each}

				<div class="flex w-full items-center justify-between gap-2">
					<p class="text-muted-foreground text-sm">Add Plex Watchlist RSS</p>
					<Form.Button
						type="button"
						size="sm"
						variant="outline"
						on:click={() => {
							addField('plex_watchlist_rss');
						}}
					>
						<Plus class="h-4 w-4" />
					</Form.Button>
				</div>
			</ArrayField>
		</div>

		<div transition:slide>
			<NumberField {form} name="plex_watchlist_update_interval" {formData} stepValue={1} />
		</div>
	{/if}

	{#if $formData.listrr_enabled}
		<div transition:slide>
			<TextField {form} name="listrr_api_key" {formData} isProtected={true} />
		</div>

		<div transition:slide>
			<NumberField {form} name="listrr_update_interval" {formData} stepValue={1} />
		</div>

		<div transition:slide>
			<ArrayField {form} name="listrr_movie_lists" {formData}>
				{#each $formData.listrr_movie_lists as _, i}
					<Form.ElementField {form} name="listrr_movie_lists[{i}]">
						<Form.Control let:attrs>
							<div class="flex items-center gap-2">
								<Input
									type="text"
									spellcheck="false"
									autocomplete="false"
									{...attrs}
									bind:value={$formData.listrr_movie_lists[i]}
								/>

								<div class="flex items-center gap-2">
									<Form.Button
										type="button"
										size="sm"
										variant="destructive"
										on:click={() => {
											removeField('listrr_movie_lists', i);
										}}
									>
										<Trash2 class="h-4 w-4" />
									</Form.Button>
								</div>
							</div>
						</Form.Control>
					</Form.ElementField>
				{/each}

				<div class="flex w-full items-center justify-between gap-2">
					<p class="text-muted-foreground text-sm">Add Listrr movie lists</p>
					<Form.Button
						type="button"
						size="sm"
						variant="outline"
						on:click={() => {
							addField('listrr_movie_lists');
						}}
					>
						<Plus class="h-4 w-4" />
					</Form.Button>
				</div>
			</ArrayField>
		</div>

		<div transition:slide>
			<ArrayField {form} name="listrr_show_lists" {formData}>
				{#each $formData.listrr_show_lists as _, i}
					<Form.ElementField {form} name="listrr_show_lists[{i}]">
						<Form.Control let:attrs>
							<div class="flex items-center gap-2">
								<Input
									type="text"
									spellcheck="false"
									autocomplete="false"
									{...attrs}
									bind:value={$formData.listrr_show_lists[i]}
								/>

								<div class="flex items-center gap-2">
									<Form.Button
										type="button"
										size="sm"
										variant="destructive"
										on:click={() => {
											removeField('listrr_show_lists', i);
										}}
									>
										<Trash2 class="h-4 w-4" />
									</Form.Button>
								</div>
							</div>
						</Form.Control>
					</Form.ElementField>
				{/each}

				<div class="flex w-full items-center justify-between gap-2">
					<p class="text-muted-foreground text-sm">Add Listrr shows lists</p>
					<Form.Button
						type="button"
						size="sm"
						variant="outline"
						on:click={() => {
							addField('listrr_show_lists');
						}}
					>
						<Plus class="h-4 w-4" />
					</Form.Button>
				</div>
			</ArrayField>
		</div>
	{/if}

	{#if $formData.trakt_enabled}
		<div transition:slide>
			<TextField {form} name="trakt_api_key" {formData} isProtected={true} />
		</div>

		<div transition:slide>
			<NumberField {form} name="trakt_update_interval" {formData} stepValue={1} />
		</div>

		<div transition:slide>
			<ArrayField {form} name="trakt_watchlist" {formData}>
				{#each $formData.trakt_watchlist as _, i}
					<Form.ElementField {form} name="trakt_watchlist[{i}]">
						<Form.Control let:attrs>
							<div class="flex items-center gap-2">
								<Input
									type="text"
									spellcheck="false"
									autocomplete="false"
									{...attrs}
									bind:value={$formData.trakt_watchlist[i]}
								/>

								<div class="flex items-center gap-2">
									<Form.Button
										type="button"
										size="sm"
										variant="destructive"
										on:click={() => {
											removeField('trakt_watchlist', i);
										}}
									>
										<Trash2 class="h-4 w-4" />
									</Form.Button>
								</div>
							</div>
						</Form.Control>
					</Form.ElementField>
				{/each}

				<div class="flex w-full items-center justify-between gap-2">
					<p class="text-muted-foreground text-sm">Add Trakt watchlist</p>
					<Form.Button
						type="button"
						size="sm"
						variant="outline"
						on:click={() => {
							addField('trakt_watchlist');
						}}
					>
						<Plus class="h-4 w-4" />
					</Form.Button>
				</div>
			</ArrayField>
		</div>

		<div transition:slide>
			<ArrayField {form} name="trakt_user_lists" {formData}>
				{#each $formData.trakt_user_lists as _, i}
					<Form.ElementField {form} name="trakt_user_lists[{i}]">
						<Form.Control let:attrs>
							<div class="flex items-center gap-2">
								<Input
									type="text"
									spellcheck="false"
									autocomplete="false"
									{...attrs}
									bind:value={$formData.trakt_user_lists[i]}
								/>

								<div class="flex items-center gap-2">
									<Form.Button
										type="button"
										size="sm"
										variant="destructive"
										on:click={() => {
											removeField('trakt_user_lists', i);
										}}
									>
										<Trash2 class="h-4 w-4" />
									</Form.Button>
								</div>
							</div>
						</Form.Control>
					</Form.ElementField>
				{/each}

				<div class="flex w-full items-center justify-between gap-2">
					<p class="text-muted-foreground text-sm">Add Trakt user watchlists</p>
					<Form.Button
						type="button"
						size="sm"
						variant="outline"
						on:click={() => {
							addField('trakt_user_lists');
						}}
					>
						<Plus class="h-4 w-4" />
					</Form.Button>
				</div>
			</ArrayField>
		</div>

		<div transition:slide>
			<CheckboxField {form} name="trakt_fetch_trending" {formData} />
		</div>

		{#if $formData.trakt_fetch_trending}
			<div transition:slide>
				<NumberField {form} name="trakt_trending_count" {formData} stepValue={1} />
			</div>
		{/if}

		<div transition:slide>
			<CheckboxField {form} name="trakt_fetch_popular" {formData} />
		</div>

		{#if $formData.trakt_fetch_popular}
			<div transition:slide>
				<NumberField {form} name="trakt_popular_count" {formData} stepValue={1} />
			</div>
		{/if}
	{/if}

	<Separator class="mt-4" />
	<div class="flex w-full justify-end">
		<Form.Button disabled={$delayed} type="submit" size="sm" class="w-full lg:max-w-max">
			{#if $delayed}
				<Loader2 class="mr-2 h-4 w-4 animate-spin" />
			{/if}
			Save changes
			<span class="ml-1" class:hidden={$page.url.pathname === '/settings/content'}
				>and continue</span
			>
		</Form.Button>
	</div>
</form>

{#if formDebug}
	<SuperDebug data={$formData} />
{/if}

<script lang="ts">
	import { slide } from 'svelte/transition';
	import { page } from '$app/stores';
	import { getContext } from 'svelte';
	import SuperDebug from 'sveltekit-superforms';
	import { zodClient } from 'sveltekit-superforms/adapters';
	import { type SuperValidated, type Infer, superForm } from 'sveltekit-superforms';
	import * as Form from '$lib/components/ui/form';
	import { generalSettingsSchema, type GeneralSettingsSchema } from '$lib/forms/helpers';
	import { toast } from 'svelte-sonner';
	import TextField from './components/text-field.svelte';
	import NumberField from './components/number-field.svelte';
	import CheckboxField from './components/checkbox-field.svelte';
	import GroupCheckboxField from './components/group-checkbox-field.svelte';
	import { Loader2 } from 'lucide-svelte';
	import { Separator } from '$lib/components/ui/separator';

	export let data: SuperValidated<Infer<GeneralSettingsSchema>>;
	export let actionUrl: string = '?/default';

	const formDebug: boolean = getContext('formDebug');

	const form = superForm(data, {
		validators: zodClient(generalSettingsSchema)
	});

	const { form: formData, enhance, message, errors, delayed } = form;

	$: if ($message && $page.status === 200) {
		toast.success($message);
	} else if ($message) {
		toast.error($message);
	}
</script>

<form method="POST" action={actionUrl} use:enhance class="my-8 flex flex-col gap-2">
	<CheckboxField {form} name="debug" {formData} fieldDescription="Requires restart" />
	<CheckboxField {form} name="log" {formData} fieldDescription="Requires restart" />
	<TextField {form} name="rclone_path" {formData} />
	<TextField {form} name="library_path" {formData} />
	<CheckboxField
		{form}
		name="separate_anime_dirs"
		{formData}
		fieldDescription="Creates anime_movies and anime_shows folders"
	/>

	<!-- movie_filesize_min, movie_filesize_max, episode_filesize_min, episode_filesize_max -->
	<NumberField
		{form}
		name="movie_filesize_min"
		label="Minimum Movie Filesize"
		{formData}
		stepValue={0.1}
		fieldDescription="Filesize in MB"
	/>
	<NumberField
		{form}
		name="movie_filesize_max"
		label="Maximum Movie Filesize"
		{formData}
		stepValue={0.1}
		fieldDescription="Filesize in MB. Set to -1 for no limit"
	/>
	<NumberField
		{form}
		name="episode_filesize_min"
		label="Minimum Episode Filesize"
		{formData}
		stepValue={0.1}
		fieldDescription="Filesize in MB"
	/>
	<NumberField
		{form}
		name="episode_filesize_max"
		label="Maximum Episode Filesize"
		{formData}
		stepValue={0.1}
		fieldDescription="Filesize in MB. Set to -1 for no limit"
	/>

	<GroupCheckboxField
		fieldTitle="Downloaders"
		fieldDescription="Enable only one downloader at a time"
	>
		<CheckboxField
			{form}
			name="realdebrid_enabled"
			label="Real-Debrid"
			{formData}
			isForGroup={true}
		/>
		<CheckboxField {form} name="torbox_enabled" label="Torbox" {formData} isForGroup={true} />
	</GroupCheckboxField>

	{#if $formData.realdebrid_enabled}
		<div transition:slide>
			<TextField {form} name="realdebrid_api_key" {formData} isProtected={true} />
		</div>

		<div transition:slide>
			<CheckboxField
				{form}
				name="realdebrid_proxy_enabled"
				label="Real-Debrid Proxy"
				{formData}
				fieldDescription="Use proxy for Real-Debrid API"
			/>
		</div>

		{#if $formData.realdebrid_proxy_enabled}
			<div transition:slide>
				<TextField {form} name="realdebrid_proxy_url" {formData} />
			</div>
		{/if}
	{/if}

	{#if $formData.torbox_enabled}
		<div transition:slide>
			<TextField {form} name="torbox_api_key" {formData} />
		</div>
	{/if}

	<Separator class="mt-4" />
	<div class="flex w-full justify-end">
		<Form.Button disabled={$delayed} type="submit" size="sm" class="w-full lg:max-w-max">
			{#if $delayed}
				<Loader2 class="mr-2 h-4 w-4 animate-spin" />
			{/if}
			Save changes
			<span class="ml-1" class:hidden={$page.url.pathname === '/settings/general'}
				>and continue</span
			>
		</Form.Button>
	</div>
</form>

{#if formDebug}
	<SuperDebug data={$formData} />
{/if}
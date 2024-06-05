<script lang="ts">
	import { superForm } from 'sveltekit-superforms/client';
	import { Button } from '$lib/components/ui/button';
	import { Separator } from '$lib/components/ui/separator';
	import { toast } from 'svelte-sonner';
	import { Loader2 } from 'lucide-svelte';
	import { page } from '$app/stores';
	import * as Form from '$lib/components/ui/form';
	import { generalSettingsSchema, type GeneralSettingsSchema } from '$lib/forms/helpers';
	import { getContext } from 'svelte';
	import type { SuperValidated } from 'sveltekit-superforms';
	import FormTextField from './components/form-text-field.svelte';
	import FormCheckboxField from './components/form-checkbox-field.svelte';
	import type { FormGroupCheckboxFieldType } from '$lib/types';
	import FormGroupCheckboxField from './components/form-group-checkbox-field.svelte';
	import { slide } from 'svelte/transition';

	let formDebug: boolean = getContext('formDebug');

	export let data: SuperValidated<GeneralSettingsSchema>;
	const generalForm = superForm(data);
	const { form, message, delayed, errors } = generalForm;

	$: if ($message && $page.status === 200) {
		toast.success($message);
	} else if ($message) {
		toast.error($message);
	}

	export let actionUrl: string = '?/default';
	const generalDownloadersFieldData: FormGroupCheckboxFieldType[] = [
		{
			field_name: 'realdebrid_enabled',
			label_name: 'Real Debrid'
		},
		{
			field_name: 'torbox_enabled',
			label_name: 'Torbox'
		}
	];
</script>

<Form.Root
	action={actionUrl}
	schema={generalSettingsSchema}
	controlled
	form={generalForm}
	let:config
	debug={formDebug}
>
	<div class="flex flex-col my-4 gap-4">
		<FormCheckboxField
			{config}
			fieldName="debug"
			fieldDescription="DEBUG is the log level, disabling it will only show INFO level."
			requiresReboot={true}
			labelName="Debug"
			errors={$errors.debug}
		/>

		<FormCheckboxField
			{config}
			fieldName="log"
			fieldDescription="Toggle logging to a file."
			requiresReboot={true}
			labelName="Log"
			errors={$errors.log}
		/>

		<FormTextField
			{config}
			fieldName="rclone_path"
			labelName="Rclone Path"
			errors={$errors.rclone_path}
		/>

		<FormTextField
			{config}
			fieldName="library_path"
			labelName="Library Path"
			errors={$errors.library_path}
		/>

		<FormGroupCheckboxField
			{config}
			fieldTitle="Downloaders"
			fieldData={generalDownloadersFieldData}
		/>

		{#if $form.realdebrid_enabled}
			<div transition:slide>
				<FormTextField
					{config}
					fieldName="realdebrid_api_key"
					isProtected={true}
					fieldValue={$form.realdebrid_api_key}
					labelName="Real Debrid API Key"
					errors={$errors.realdebrid_api_key}
				/>
			</div>
		{/if}

		{#if $form.torbox_enabled}
			<div transition:slide>
				<FormTextField
					{config}
					fieldName="torbox_api_key"
					isProtected={true}
					fieldValue={$form.torbox_api_key}
					labelName="Torbox API Key"
					errors={$errors.torbox_api_key}
				/>
			</div>
		{/if}

		<Separator class=" mt-4" />
		<div class="flex w-full justify-end">
			<Button
				disabled={$delayed}
				type="submit"
				size="sm"
				class="w-full md:max-w-max font-semibold text-xs"
			>
				{#if $delayed}
					<Loader2 class="w-4 h-4 animate-spin mr-2" />
				{/if}
				Save changes
				<span class="ml-1" class:hidden={$page.url.pathname === '/settings/general'}
					>and continue</span
				>
			</Button>
		</div>
	</div>
</Form.Root>

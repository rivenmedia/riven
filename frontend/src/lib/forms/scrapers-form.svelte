<script lang="ts">
	import { slide } from 'svelte/transition';
	import { superForm } from 'sveltekit-superforms/client';
	import { Button } from '$lib/components/ui/button';
	import { Separator } from '$lib/components/ui/separator';
	import { toast } from 'svelte-sonner';
	import { Loader2 } from 'lucide-svelte';
	import { page } from '$app/stores';
	import * as Form from '$lib/components/ui/form';
	import { scrapersSettingsSchema, type ScrapersSettingsSchema } from '$lib/forms/helpers';
	import { getContext } from 'svelte';
	import type { SuperValidated } from 'sveltekit-superforms';
	import FormTextField from './components/form-text-field.svelte';
	import FormNumberField from './components/form-number-field.svelte';
	import FormGroupCheckboxField from './components/form-group-checkbox-field.svelte';
	import type { FormGroupCheckboxFieldType } from '$lib/types';

	let formDebug: boolean = getContext('formDebug');

	export let data: SuperValidated<ScrapersSettingsSchema>;
	const scrapersForm = superForm(data);
	const { form, message, delayed, errors } = scrapersForm;

	$: if ($message && $page.status === 200) {
		toast.success($message);
	} else if ($message) {
		toast.error($message);
	}

	export let actionUrl: string = '?/default';

	const scrapersEnabledFieldData: FormGroupCheckboxFieldType[] = [
		{
			field_name: 'torrentio_enabled',
			label_name: 'Torrentio'
		},
		{
			field_name: 'orionoid_enabled',
			label_name: 'Orionoid'
		},
		{
			field_name: 'jackett_enabled',
			label_name: 'Jackett'
		}
	];
</script>

<Form.Root
	action={actionUrl}
	schema={scrapersSettingsSchema}
	controlled
	form={scrapersForm}
	let:config
	debug={formDebug}
>
	<div class="flex flex-col my-4 gap-4">
		<FormNumberField
			{config}
			fieldName="after_2"
			fieldDescription="Time to wait after 2 failed attempts in hours."
			stepValue={0.01}
			labelName="After 2"
			errors={$errors.after_2}
		/>
		<FormNumberField
			{config}
			fieldName="after_5"
			fieldDescription="Time to wait after 5 failed attempts in hours."
			stepValue={0.01}
			labelName="After 5"
			errors={$errors.after_5}
		/>
		<FormNumberField
			{config}
			fieldName="after_10"
			fieldDescription="Time to wait after 10 failed attempts in hours."
			stepValue={0.01}
			labelName="After 10"
			errors={$errors.after_10}
		/>

		<FormGroupCheckboxField
			{config}
			fieldTitle="Scrapers Enabled"
			fieldData={scrapersEnabledFieldData}
		/>

		{#if $form.torrentio_enabled}
			<div transition:slide>
				<FormTextField
					{config}
					fieldName="torrentio_url"
					labelName="Torrentio URL"
					errors={$errors.torrentio_url}
				/>
			</div>

			<div transition:slide>
				<FormTextField
					{config}
					fieldName="torrentio_filter"
					labelName="Torrentio Filter"
					errors={$errors.torrentio_filter}
				/>
			</div>
		{/if}

		{#if $form.orionoid_enabled}
			<div transition:slide>
				<FormTextField
					{config}
					fieldName="orionoid_api_key"
					isProtected={true}
					fieldValue={$form.orionoid_api_key}
					labelName="Orionoid API Key"
					errors={$errors.orionoid_api_key}
				/>
			</div>
		{/if}

		{#if $form.jackett_enabled}
			<div transition:slide>
				<FormTextField
					{config}
					fieldName="jackett_url"
					labelName="Jackett URL"
					errors={$errors.jackett_url}
				/>
			</div>

			<div transition:slide>
				<FormTextField
					{config}
					fieldName="jackett_api_key"
					isProtected={true}
					fieldValue={$form.jackett_api_key}
					fieldDescription="Optional field if Jackett is not password protected."
					labelName="Jackett API Key"
					errors={$errors.jackett_api_key}
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
				<span class="ml-1" class:hidden={$page.url.pathname === '/settings/scrapers'}
					>and continue</span
				>
			</Button>
		</div>
	</div>
</Form.Root>

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
			requiresReboot={true}
			labelName="Debug"
			errors={$errors.debug}
		/>

		<FormCheckboxField
			{config}
			fieldName="log"
			requiresReboot={true}
			labelName="Log"
			errors={$errors.log}
		/>

		<FormTextField
			{config}
			fieldName="host_path"
			labelName="Host Path"
			errors={$errors.host_path}
		/>

		<FormTextField
			{config}
			fieldName="container_path"
			labelName="Container Path"
			errors={$errors.container_path}
		/>

		<!-- <FormProtectedField
			{config}
			fieldName="realdebrid_api_key"
			fieldValue={$form.realdebrid_api_key}
			labelName="Real Debrid API Key"
			errors={$errors.realdebrid_api_key}
		/> -->

		<FormTextField
			{config}
			fieldName="realdebrid_api_key"
			isProtected={true}
			fieldValue={$form.realdebrid_api_key}
			labelName="Real Debrid API Key"
			errors={$errors.realdebrid_api_key}
		/>

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

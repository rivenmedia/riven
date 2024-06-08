<script lang="ts">
	import { generalSettingsSchema, type GeneralSettingsSchema } from '$lib/forms/helpers';
	import { type SuperValidated, type Infer, superForm } from 'sveltekit-superforms';
	import * as Form from '$lib/components/ui/form';
    import { Label } from "$lib/components/ui/label"
    import { Input } from "$lib/components/ui/input"
	import { zodClient } from 'sveltekit-superforms/adapters';
	import { toast } from 'svelte-sonner';
	import { page } from '$app/stores';
	import FormTextField from './components/form-text-field.svelte';
	import SuperDebug from 'sveltekit-superforms';

	export let data: SuperValidated<Infer<GeneralSettingsSchema>>;

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

<form method="POST" use:enhance>
	<FormTextField
		{form}
		fieldName="realdebrid_api_key"
		fieldValue={$formData.realdebrid_api_key}
		labelName="Realdebrid API Key"
		fieldDescription="Realdebrid API Key here"
	/>

    <Form.Field {form} name="realdebrid_api_key">
		<Form.Control let:attrs>
			<Label>Name</Label>
			<Input {...attrs} bind:value={$formData.realdebrid_api_key} />
		</Form.Control>
		<Form.Description>lorem ipsum</Form.Description>
		<Form.FieldErrors />
	</Form.Field>

	<Form.Button>Submit</Form.Button>
</form>

<SuperDebug data={$formData} />

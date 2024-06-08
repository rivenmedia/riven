<script lang="ts">
	import { formatWords } from '$lib/helpers';
	import * as Form from '$lib/components/ui/form';
	import { Input } from '$lib/components/ui/input';
	import clsx from 'clsx';

	export let form: any;
	export let fieldName: string;
	export let fieldDescription: string | undefined = undefined;
	export let isProtected: boolean = false;
	export let fieldValue: string = '';
	export let labelName: string = formatWords(fieldName);
</script>

<Form.Field {form} name={fieldName}>
	<Form.Control let:attrs>
		<Form.Label>{labelName}</Form.Label>
		<Input {...attrs} bind:value={fieldValue} />
	</Form.Control>
	{#if fieldDescription}
		<Form.Description>{fieldDescription}</Form.Description>
	{/if}

	<Form.FieldErrors />
</Form.Field>

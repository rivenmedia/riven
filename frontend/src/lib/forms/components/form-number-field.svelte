<script lang="ts">
	import { formatWords } from '$lib/helpers';
	import * as Form from '$lib/components/ui/form';

	export let config: any;
	export let fieldName: string;
	export let stepValue: number | undefined;
	export let labelName: string = formatWords(fieldName);
	export let errors: string[] | undefined;
</script>

<Form.Field {config} name={fieldName}>
	<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
		<Form.Label class="font-semibold w-48 min-w-48 text-muted-foreground">
			{labelName}
		</Form.Label>
		{#if stepValue}
			<Form.Input type="number" step={stepValue} spellcheck="false" />
		{:else}
			<Form.Input type="number" spellcheck="false" />
		{/if}
	</Form.Item>
	{#if errors}
		<Form.Validation class="text-sm text-red-500" />
	{/if}
</Form.Field>

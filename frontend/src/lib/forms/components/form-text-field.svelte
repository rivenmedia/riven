<script lang="ts">
	import { formatWords } from '$lib/helpers';
	import * as Form from '$lib/components/ui/form';
	import clsx from 'clsx';

	export let config: any;
	export let fieldName: string;
	export let isProtected: boolean = false;
	export let fieldValue: string = '';
	export let labelName: string = formatWords(fieldName);
	export let errors: string[] | undefined;
</script>

<Form.Field {config} name={fieldName}>
	<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
		<Form.Label class="font-semibold w-48 min-w-48 text-muted-foreground">
			{labelName}
		</Form.Label>
		{#if isProtected}
			<Form.Input
				class={clsx('transition-all duration-300', {
					'blur-sm hover:blur-none focus:blur-none': fieldValue.length > 0
				})}
				spellcheck="false"
			/>
		{:else}
			<Form.Input spellcheck="false" />
		{/if}
	</Form.Item>
	{#if errors}
		<Form.Validation class="text-sm text-red-500" />
	{/if}
</Form.Field>

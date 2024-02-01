<script lang="ts">
	import { formatWords } from '$lib/helpers';
	import * as Form from '$lib/components/ui/form';
	import clsx from 'clsx';

	export let config: any;
	export let fieldName: string;
	export let fieldDescription: string | undefined = undefined;
	export let requiresReboot: boolean = false;
	export let labelName: string = formatWords(fieldName);
	export let errors: string[] | undefined;
</script>

<Form.Field {config} name={fieldName}>
	<Form.Item
		class={clsx('flex flex-col md:flex-row items-start max-w-6xl md:gap-4', {
			'md:items-center': !fieldDescription
		})}
	>
		<div class="flex flex-col items-start w-full md:w-48 min-w-48 gap-1">
			<Form.Label class="font-semibold">
				{labelName}

				{#if requiresReboot}
					<span class="text-red-500">*</span>
				{/if}
			</Form.Label>
			{#if fieldDescription}
				<Form.Description class="text-xs text-muted-foreground">
					{fieldDescription}
				</Form.Description>
			{/if}
		</div>

		<Form.Checkbox />
	</Form.Item>
	{#if errors}
		<Form.Validation class="text-sm text-red-500" />
	{/if}
</Form.Field>

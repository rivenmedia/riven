<script lang="ts">
	import * as Form from '$lib/components/ui/form';
	import type { FormGroupCheckboxFieldType } from '$lib/types';
	import clsx from 'clsx';

	export let config: any;
	export let fieldTitle: string;
	export let fieldDescription: string | undefined = undefined;
	export let fieldData: FormGroupCheckboxFieldType[];
</script>

<div
	class={clsx('flex flex-col md:flex-row items-start max-w-6xl gap-2 md:gap-4', {
		'md:items-center': !fieldDescription
	})}
>
	<div class="flex flex-col items-start w-full md:w-48 min-w-48 gap-1">
		<p class="font-semibold text-sm">{fieldTitle}</p>
		{#if fieldDescription}
			<p class="text-xs text-muted-foreground">{fieldDescription}</p>
		{/if}
	</div>

	<div class="flex flex-wrap gap-4">
		{#each fieldData as field}
			<Form.Field {config} name={field.field_name}>
				<div class="flex flex-wrap items-center gap-2">
					<Form.Checkbox />
					<Form.Label>{field.label_name}</Form.Label>
				</div>
			</Form.Field>
		{/each}
	</div>
</div>

<script lang="ts">
	import { formatWords } from '$lib/helpers';
	import * as Form from '$lib/components/ui/form';
	import type { FormGroupCheckboxFieldType } from '$lib/types';

	export let config: any;
	export let fieldTitle: string;
	export let fieldData: FormGroupCheckboxFieldType[];
</script>

<div class="flex flex-col md:flex-row items-start md:items-center max-w-6xl gap-2">
	<p class="font-semibold w-48 min-w-48 text-sm text-muted-foreground">{fieldTitle}</p>
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

<script lang="ts" context="module">
	// eslint-disable-next-line @typescript-eslint/no-unused-vars
	import type { FormPath } from 'sveltekit-superforms';

	type T = Record<string, unknown>;
	type U = unknown;
</script>

<script lang="ts" generics="T extends Record<string, unknown>, U extends FormPath<T>">
	import { type FieldsetProps } from 'formsnap';
	import clsx from 'clsx';
	import * as Form from '$lib/components/ui/form';
	import type { SuperForm } from 'sveltekit-superforms';
	import type { Writable } from 'svelte/store';
	import { formatWords } from '$lib/helpers';

	type $$Props = FieldsetProps<T, U> & {
		legend?: string;
		fieldDescription?: string;
		formData: Writable<any>;
	};

	export let form: SuperForm<T>;
	export let name: U;
	export let legend: string = formatWords(name as string);
	export let fieldDescription: string | undefined = undefined;
	export let formData: Writable<any>;
</script>

<Form.Fieldset {form} {name}>
	<div
		class={clsx('flex max-w-6xl flex-col items-start gap-2 md:flex-row md:gap-4', {
			'md:items-center': !fieldDescription
		})}
	>
		<div class="flex w-full min-w-48 flex-col items-start gap-2 md:w-48">
			<Form.Legend>{legend}</Form.Legend>
			{#if fieldDescription}
				<p class="text-muted-foreground text-xs">{fieldDescription}</p>
			{/if}
		</div>

		<div class="flex flex-col items-start gap-2">
			{#each $formData[name] as _, i}
				<Form.ElementField {form} name="{name}[{i}]">
					<Form.Control let:attrs>
						<input type="text" {...attrs} bind:value={$formData[name][i]} />
					</Form.Control>
				</Form.ElementField>
			{/each}
		</div>

		<Form.FieldErrors class="mt-2 text-xs text-red-500" />
	</div>
</Form.Fieldset>

<script lang="ts" context="module">
	// eslint-disable-next-line @typescript-eslint/no-unused-vars
	import type { FormPath } from 'sveltekit-superforms';

	type T = Record<string, unknown>;
	type U = unknown;
</script>

<script lang="ts" generics="T extends Record<string, unknown>, U extends FormPath<T>">
	import { Control, Label, type ControlProps, Field, type FieldProps, FieldErrors } from 'formsnap';
	import clsx from 'clsx';
	import type { Writable } from 'svelte/store';
	import { Input } from '$lib/components/ui/input';
	import type { SuperForm } from 'sveltekit-superforms';
	import { formatWords } from '$lib/helpers';
	import * as Form from '$lib/components/ui/form';

	type $$Props = FieldProps<T, U> &
		ControlProps & {
			label?: string;
			fieldDescription?: string;
			formData: Writable<any>;
			stepValue: number | undefined;
		};

	export let form: SuperForm<T>;
	export let name: U;
	export let label: string = formatWords(name as string);
	export let fieldDescription: string | undefined = undefined;
	export let formData: Writable<any>;
	export let stepValue: number | undefined;
</script>

<Form.Field {form} {name} let:value let:errors let:tainted let:constraints>
	<Form.Control let:attrs {...$$restProps}>
		<div
			class={clsx('flex max-w-6xl flex-col items-start gap-2 md:flex-row md:gap-4', {
				'md:items-center': !fieldDescription
			})}
		>
			<div class="flex w-full min-w-48 flex-col items-start gap-2 md:w-48">
				<Form.Label>{label}</Form.Label>
				{#if fieldDescription}
					<p class="text-xs text-muted-foreground">{fieldDescription}</p>
				{/if}
			</div>
			<Input {...attrs} type="number" step={stepValue} bind:value={$formData[name]} />
		</div>
	</Form.Control>

	<Form.FieldErrors class="mt-2 text-xs text-red-500" />
</Form.Field>

<script lang="ts">
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { toast } from 'svelte-sonner';
	import { fly } from 'svelte/transition';
	import { X } from 'lucide-svelte';
	import { type Writable } from 'svelte/store';
	import clsx from 'clsx';

	// read comment below in html
	export let fieldName: string;
	export let fieldDescription: string | undefined = undefined;
	export let labelName: string;
	export let fieldValue: Writable<string[]>;
	export let numberValidate: boolean = false;

	let current_field_value = '';

	function addToList(event: SubmitEvent) {
		event.preventDefault();

		if (numberValidate) {
			if (isNaN(Number(current_field_value))) {
				current_field_value = '';
				toast.error('Must be a number');
				return;
			}
		}

		if ($fieldValue.includes(current_field_value)) {
			toast.error('Already in list');
			return;
		}

		$fieldValue = [...$fieldValue.filter((item: any) => item !== ''), current_field_value];
		current_field_value = '';
	}

	function removeFromList(list: string) {
		$fieldValue = $fieldValue.filter((item: any) => item !== list);
		if ($fieldValue.length === 0) {
			$fieldValue = [''];
		}
	}
</script>

<!--This component requires that you make a hidden select element-->

<div
	class={clsx('flex flex-col md:flex-row items-start max-w-6xl gap-2 md:gap-4', {
		'md:items-center': !fieldDescription
	})}
>
	<div class="flex flex-col items-start w-full md:w-48 min-w-48 gap-1">
		<Label for={fieldName} class="font-semibold">
			{labelName}
		</Label>
		{#if fieldDescription}
			<p class="text-xs text-muted-foreground">{fieldDescription}</p>
		{/if}
	</div>

	<form on:submit={addToList} class="w-full flex flex-col gap-4 items-start">
		<Input
			placeholder="Enter list numbers one at a time"
			class="w-full"
			bind:value={current_field_value}
		/>
		<div class="flex items-center w-full flex-wrap gap-2">
			{#each $fieldValue.filter((list) => list !== '') as list (list)}
				<button
					type="button"
					in:fly={{ y: 10, duration: 200 }}
					out:fly={{ y: -10, duration: 200 }}
					class="flex items-center justify-between gap-2 py-1 px-6 text-sm bg-secondary rounded-md"
					on:click={() => removeFromList(list)}
				>
					<p>{list}</p>
					<X class="w-4 h-4 text-red-500" />
				</button>
			{/each}
		</div>
	</form>
</div>

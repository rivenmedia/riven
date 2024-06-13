<script lang="ts">
	import clsx from 'clsx';

	type $$$Props = {
		fieldTitle: string;
		fieldDescription?: string;
	};

	export let fieldTitle: string;
	export let fieldDescription: string | undefined;
</script>

<div
	class={clsx('flex max-w-6xl flex-col items-start gap-2 md:flex-row md:gap-4', {
		'md:items-center': !fieldDescription
	})}
>
	<div class="flex w-full min-w-48 flex-col items-start gap-1 md:w-48">
		<p class="text-sm">{fieldTitle}</p>
		{#if fieldDescription}
			<p class="text-xs text-muted-foreground">{fieldDescription}</p>
		{/if}
	</div>

	<div class="flex flex-wrap gap-4">
		<slot />
	</div>
</div>

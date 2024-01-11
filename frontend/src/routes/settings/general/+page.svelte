<script lang="ts">
	import type { PageData } from './$types';
	import * as Accordion from '$lib/components/ui/accordion';
	import GeneralForm from '$lib/forms/general-form.svelte';

	export let data: PageData;
</script>

<div class="flex flex-col">
	<h2 class="text-2xl md:text-3xl font-semibold">General Settings</h2>
	<p class="text-base md:text-lg text-muted-foreground">
		Configure global and default settings for Iceberg.
	</p>
	<Accordion.Root>
		<Accordion.Item value="debug-vs-log">
			<Accordion.Trigger class="text-base md:text-lg font-normal"
				>What is the difference in debug and log?</Accordion.Trigger
			>
			<Accordion.Content class="text-sm md:text-base"
				>DEBUG is the log level, if you turn it off you will only see INFO in the logs. LOG on
				another hand means logging to file.</Accordion.Content
			>
		</Accordion.Item>
	</Accordion.Root>

	<p class="text-sm md:text-base text-muted-foreground mt-4">
		* These settings require a restart to take effect.
	</p>

	<GeneralForm data={data.form} />
</div>

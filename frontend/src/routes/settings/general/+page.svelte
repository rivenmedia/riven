<script lang="ts">
	import * as Form from '$lib/components/ui/form';
	import { Separator } from '$lib/components/ui/separator';
	import { generalSettingsSchema, type GeneralSettingsSchema } from '$lib/schemas/setting';
	import { toast } from 'svelte-sonner';
	import type { SuperValidated } from 'sveltekit-superforms';

	export let form: SuperValidated<GeneralSettingsSchema>;
	export let data: any;
</script>

<pre>{JSON.stringify(data, null, 2)}</pre>
<pre>{JSON.stringify(form, null, 2)}</pre>

<Form.Root method="POST" {form} schema={generalSettingsSchema} let:config>
	<Form.Field {config} name="host_mount">
		<Form.Item>
			<Form.Label class="text-xl">Host Mount</Form.Label>
			<Form.Input class="text-base" />
			<Form.Description>This is your host mount</Form.Description>
			<Form.Validation />
		</Form.Item>
	</Form.Field>
	<Form.Field {config} name="container_mount">
		<Form.Item>
			<Form.Label class="text-xl">Container Mount</Form.Label>
			<Form.Input class="text-base" />
			<Form.Description>This is your container mount</Form.Description>
			<Form.Validation />
		</Form.Item>
	</Form.Field>
	<Form.Field {config} name="realdebrid_api_key">
		<Form.Item>
			<Form.Label class="text-xl">Realdebrid API Key</Form.Label>
			<Form.Input
				class="text-base blur-sm hover:blur-none focus:blur-none transition-all duration-300"
			/>
			<Form.Description>This is your realdebrid api key</Form.Description>
			<Form.Validation />
		</Form.Item>
	</Form.Field>
	<Form.Field {config} name="torrentio_filter">
		<Form.Item>
			<Form.Label class="text-xl">Torrentio Filter</Form.Label>
			<Form.Input class="text-base" />
			<Form.Description>This is your torrentio filter</Form.Description>
			<Form.Validation />
		</Form.Item>
	</Form.Field>
	<Separator class="my-8 p-1 w-full" />

	<div class="flex w-full justify-end">
		<Form.Button size="sm">Save changes</Form.Button>
	</div>
</Form.Root>

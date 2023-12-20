<script lang="ts">
	import * as Form from '$lib/components/ui/form';
	import { Separator } from '$lib/components/ui/separator';

	import { generalSettingsSchema, type GeneralSettingsSchema } from '$lib/schemas/setting';
	import type { SuperValidated } from 'sveltekit-superforms';
	export let form: SuperValidated<GeneralSettingsSchema>;

	export let data: any;
</script>

<!-- <pre>{JSON.stringify(data, null, 2)}</pre> -->

<Form.Root method="POST" {form} schema={generalSettingsSchema} let:config>
	<Form.Field {config} name="host_mount">
		<Form.Item class="*:text-base">
			<Form.Label>Host Mount</Form.Label>
			<Form.Input value={data.settings.host_mount.data} />
			<Form.Description>This is your host mount</Form.Description>
			<Form.Validation />
		</Form.Item>
	</Form.Field>
	<Form.Field {config} name="container_mount">
		<Form.Item class="*:text-base">
			<Form.Label>Container Mount</Form.Label>
			<Form.Input value={data.settings.container_mount.data} />
			<Form.Description>This is your container mount</Form.Description>
			<Form.Validation />
		</Form.Item>
	</Form.Field>
	<Form.Field {config} name="realdebrid_api_key">
		<Form.Item class="*:text-base">
			<Form.Label>Realdebrid API Key</Form.Label>
			<Form.Input value={data.settings.realdebrid.data.api_key} />
			<Form.Description>This is your realdebrid api key</Form.Description>
			<Form.Validation />
		</Form.Item>
	</Form.Field>
	<Form.Field {config} name="torrentio_filter">
		<Form.Item class="*:text-base">
			<Form.Label>Torrentio Filter</Form.Label>
			<Form.Input value={data.settings.torrentio.data.filter} />
			<Form.Description>This is your torrentio filter</Form.Description>
			<Form.Validation />
		</Form.Item>
	</Form.Field>
	<Separator class="my-4 w-full" />

	<div class="flex w-full justify-end">
		<Form.Button>Save changes</Form.Button>
	</div>
</Form.Root>

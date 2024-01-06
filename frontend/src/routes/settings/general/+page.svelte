<script lang="ts">
	import type { PageData } from './$types';
	import { slide } from 'svelte/transition';
	import { superForm } from 'sveltekit-superforms/client';
	import { Button } from '$lib/components/ui/button';
	import { Separator } from '$lib/components/ui/separator';
	import { toast } from 'svelte-sonner';
	import { Loader2 } from 'lucide-svelte';
	import { page } from '$app/stores';
	import clsx from 'clsx';
	import * as Form from '$lib/components/ui/form';
	import { generalSettingsSchema, type GeneralSettingsSchema } from '$lib/schemas/setting';
	import { getContext } from 'svelte';

	let formDebug: boolean = getContext('formDebug');

	export let data: PageData;
	const generalForm = superForm(data.form);
	const { form, message, delayed } = generalForm;

	$: if ($message && $page.status === 200) {
		toast.success($message);
	} else if ($message) {
		toast.error($message);
	}
</script>

<div class="flex flex-col">
	<h2 class="text-2xl md:text-3xl font-semibold">General Settings</h2>
	<p class="text-base md:text-lg text-muted-foreground">
		Configure global and default settings for Iceberg.
	</p>
	<p class="text-sm md:text-base text-muted-foreground">
		* These settings require a restart to take effect.
	</p>

	<Form.Root
		schema={generalSettingsSchema}
		controlled
		form={generalForm}
		let:config
		debug={formDebug}
	>
		<div class="flex flex-col my-4 gap-4">
			<Form.Field {config} name="debug">
				<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
					<Form.Label
						class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
					>
						Debug *
					</Form.Label>
					<Form.Checkbox class="text-sm md:text-base" />
				</Form.Item>
				<Form.Validation class="text-sm md:text-base text-red-500" />
			</Form.Field>

			<Form.Field {config} name="log">
				<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
					<Form.Label
						class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
					>
						Log *
					</Form.Label>
					<Form.Checkbox class="text-sm md:text-base" />
				</Form.Item>
				<Form.Validation class="text-sm md:text-base text-red-500" />
			</Form.Field>

			<Form.Field {config} name="host_path">
				<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
					<Form.Label
						class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
					>
						Host Path
					</Form.Label>
					<Form.Input class="text-sm md:text-base" spellcheck="false" />
				</Form.Item>
				<Form.Validation class="text-sm md:text-base text-red-500" />
			</Form.Field>

			<Form.Field {config} name="container_path">
				<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
					<Form.Label
						class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
					>
						Container Path
					</Form.Label>
					<Form.Input class="text-sm md:text-base" spellcheck="false" />
				</Form.Item>
				<Form.Validation class="text-sm md:text-base text-red-500" />
			</Form.Field>

			<Form.Field {config} name="realdebrid_api_key">
				<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
					<Form.Label
						class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
					>
						Real Debrid API Key
					</Form.Label>
					<Form.Input
						class={clsx('transition-all duration-300 text-sm md:text-base', {
							'blur-sm hover:blur-none focus:blur-none': $form.realdebrid_api_key.length > 0
						})}
						spellcheck="false"
					/>
				</Form.Item>
				<Form.Validation class="text-sm md:text-base text-red-500" />
			</Form.Field>

			<Separator class=" mt-4" />
			<div class="flex w-full justify-end">
				<Button disabled={$delayed} type="submit" size="sm" class="w-full md:max-w-max">
					{#if $delayed}
						<Loader2 class="w-4 h-4 animate-spin mr-2" />
					{/if}
					Save changes
				</Button>
			</div>
		</div>
	</Form.Root>
</div>

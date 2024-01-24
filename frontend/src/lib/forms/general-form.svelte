<script lang="ts">
	import { superForm } from 'sveltekit-superforms/client';
	import { Button } from '$lib/components/ui/button';
	import { Separator } from '$lib/components/ui/separator';
	import { toast } from 'svelte-sonner';
	import { Loader2 } from 'lucide-svelte';
	import { page } from '$app/stores';
	import clsx from 'clsx';
	import * as Form from '$lib/components/ui/form';
	import { generalSettingsSchema, type GeneralSettingsSchema } from '$lib/forms/helpers';
	import { getContext } from 'svelte';
	import type { SuperValidated } from 'sveltekit-superforms';

	let formDebug: boolean = getContext('formDebug');

	export let data: SuperValidated<GeneralSettingsSchema>;
	const generalForm = superForm(data);
	const { form, message, delayed, errors } = generalForm;

	$: if ($message && $page.status === 200) {
		toast.success($message);
	} else if ($message) {
		toast.error($message);
	}

	export let actionUrl: string = '?/default';
</script>

<Form.Root
	action={actionUrl}
	schema={generalSettingsSchema}
	controlled
	form={generalForm}
	let:config
	debug={formDebug}
>
	<div class="flex flex-col my-4 gap-4">
		<Form.Field {config} name="debug">
			<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
				<Form.Label class="font-semibold w-48 min-w-48 text-muted-foreground"
					>Debug <span class="text-red-500">*</span></Form.Label
				>
				<Form.Checkbox />
			</Form.Item>
			{#if $errors.debug}
				<Form.Validation class="text-sm text-red-500" />
			{/if}
		</Form.Field>

		<Form.Field {config} name="log">
			<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
				<Form.Label class="font-semibold w-48 min-w-48 text-muted-foreground">Log <span class="text-red-500">*</span></Form.Label>
				<Form.Checkbox />
			</Form.Item>
			{#if $errors.log}
				<Form.Validation class="text-sm text-red-500" />
			{/if}
		</Form.Field>

		<Form.Field {config} name="host_path">
			<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
				<Form.Label class="font-semibold w-48 min-w-48 text-muted-foreground">Host Path</Form.Label>
				<Form.Input spellcheck="false" />
			</Form.Item>
			{#if $errors.host_path}
				<Form.Validation class="text-sm text-red-500" />
			{/if}
		</Form.Field>

		<Form.Field {config} name="container_path">
			<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
				<Form.Label class="font-semibold w-48 min-w-48 text-muted-foreground">
					Container Path
				</Form.Label>
				<Form.Input spellcheck="false" />
			</Form.Item>
			{#if $errors.container_path}
				<Form.Validation class="text-sm text-red-500" />
			{/if}
		</Form.Field>

		<Form.Field {config} name="realdebrid_api_key">
			<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
				<Form.Label class="font-semibold w-48 min-w-48 text-muted-foreground">
					Real Debrid API Key
				</Form.Label>
				<Form.Input
					class={clsx('transition-all duration-300', {
						'blur-sm hover:blur-none focus:blur-none': $form.realdebrid_api_key.length > 0
					})}
					spellcheck="false"
				/>
			</Form.Item>
			{#if $errors.realdebrid_api_key}
				<Form.Validation class="text-sm text-red-500" />
			{/if}
		</Form.Field>

		<Separator class=" mt-4" />
		<div class="flex w-full justify-end">
			<Button
				disabled={$delayed}
				type="submit"
				size="sm"
				class="w-full md:max-w-max font-semibold text-xs"
			>
				{#if $delayed}
					<Loader2 class="w-4 h-4 animate-spin mr-2" />
				{/if}
				Save changes
				<span class="ml-1" class:hidden={$page.url.pathname === '/settings/general'}
					>and continue</span
				>
			</Button>
		</div>
	</div>
</Form.Root>

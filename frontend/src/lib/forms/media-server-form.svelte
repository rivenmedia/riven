<script lang="ts">
	import { superForm } from 'sveltekit-superforms/client';
	import { Button } from '$lib/components/ui/button';
	import { Separator } from '$lib/components/ui/separator';
	import { toast } from 'svelte-sonner';
	import { Loader2 } from 'lucide-svelte';
	import { page } from '$app/stores';
	import clsx from 'clsx';
	import * as Form from '$lib/components/ui/form';
	import { mediaServerSettingsSchema, type MediaServerSettingsSchema } from '$lib/schemas/setting';
	import { getContext } from 'svelte';
	import type { SuperValidated } from 'sveltekit-superforms';

	let formDebug: boolean = getContext('formDebug');

	export let data: SuperValidated<MediaServerSettingsSchema>;
	const mediaServerForm = superForm(data);
	const { form, message, delayed, errors } = mediaServerForm;

	$: if ($message && $page.status === 200) {
		toast.success($message);
	} else if ($message) {
		toast.error($message);
	}

	export let actionUrl: string = "?/default"
</script>

<Form.Root
	action={actionUrl}
	schema={mediaServerSettingsSchema}
	controlled
	form={mediaServerForm}
	let:config
	debug={formDebug}
>
	<div class="flex flex-col my-4 gap-4">
		<Form.Field {config} name="plex_url">
			<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
				<Form.Label class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground">
					Plex URL
				</Form.Label>
				<Form.Input class="text-sm md:text-base" spellcheck="false" />
			</Form.Item>
			{#if $errors.plex_url}
				<Form.Validation class="text-sm md:text-base text-red-500" />
			{/if}
		</Form.Field>

		<Form.Field {config} name="plex_token">
			<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
				<Form.Label class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground">
					Plex Token
				</Form.Label>
				<Form.Input
					class={clsx('transition-all duration-300 text-sm md:text-base', {
						'blur-sm hover:blur-none focus:blur-none': $form.plex_token.length > 0
					})}
					spellcheck="false"
				/>
			</Form.Item>
			{#if $errors.plex_token}
				<Form.Validation class="text-sm md:text-base text-red-500" />
			{/if}
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

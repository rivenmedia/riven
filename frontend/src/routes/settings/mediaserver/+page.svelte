<script lang="ts">
	import type { PageData } from './$types';
	import { superForm } from 'sveltekit-superforms/client';
	import { Button } from '$lib/components/ui/button';
	import { Separator } from '$lib/components/ui/separator';
	import { toast } from 'svelte-sonner';
	import { Loader2 } from 'lucide-svelte';
	import { page } from '$app/stores';
	import clsx from 'clsx';
	import * as Form from '$lib/components/ui/form';
	import { mediaServerSettingsSchema, type MediaServerSettingsSchema } from '$lib/schemas/setting';

	export let data: PageData;
	const mediaServerForm = superForm(data.form);
	const { form, message, delayed } = mediaServerForm;

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

	<Form.Root
		schema={mediaServerSettingsSchema}
		controlled
		form={mediaServerForm}
		let:config
		debug={false}
	>
		<div class="flex flex-col my-4 gap-4">
			<Form.Field {config} name="plex_url">
				<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
					<Form.Label
						class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
					>
						Plex URL
					</Form.Label>
					<Form.Input class="text-sm md:text-base" spellcheck="false" />
				</Form.Item>
				<Form.Validation class="text-sm md:text-base text-red-500" />
			</Form.Field>

			<Form.Field {config} name="plex_token">
				<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
					<Form.Label
						class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
					>
						Plex Token
					</Form.Label>
					<Form.Input
						class={clsx('transition-all duration-300 text-sm md:text-base', {
							'blur-sm hover:blur-none focus:blur-none': $form.plex_token.length > 0
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

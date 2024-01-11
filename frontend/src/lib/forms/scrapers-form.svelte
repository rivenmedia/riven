<script lang="ts">
	import { slide } from 'svelte/transition';
	import { superForm } from 'sveltekit-superforms/client';
	import { Button } from '$lib/components/ui/button';
	import { Separator } from '$lib/components/ui/separator';
	import { toast } from 'svelte-sonner';
	import { Loader2 } from 'lucide-svelte';
	import { page } from '$app/stores';
	import clsx from 'clsx';
	import * as Form from '$lib/components/ui/form';
	import { scrapersSettingsSchema, type ScrapersSettingsSchema } from '$lib/schemas/setting';
	import { getContext } from 'svelte';
	import type { SuperValidated } from 'sveltekit-superforms';

	let formDebug: boolean = getContext('formDebug');

	export let data: SuperValidated<ScrapersSettingsSchema>;
	const scrapersForm = superForm(data);
	const { form, message, delayed } = scrapersForm;

	$: if ($message && $page.status === 200) {
		toast.success($message);
	} else if ($message) {
		toast.error($message);
	}
</script>

<Form.Root
	schema={scrapersSettingsSchema}
	controlled
	form={scrapersForm}
	let:config
	debug={formDebug}
>
	<div class="flex flex-col my-4 gap-4">
		<Form.Field {config} name="after_2">
			<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
				<Form.Label class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground">
					Retry After 2 Times (hr)
				</Form.Label>
				<Form.Input type="number" step="0.01" class="text-sm md:text-base" spellcheck="false" />
			</Form.Item>
			<Form.Validation class="text-sm md:text-base text-red-500" />
		</Form.Field>

		<Form.Field {config} name="after_5">
			<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
				<Form.Label class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground">
					Retry After 5 Times (hr)
				</Form.Label>
				<Form.Input type="number" step="0.01" class="text-sm md:text-base" spellcheck="false" />
			</Form.Item>
			<Form.Validation class="text-sm md:text-base text-red-500" />
		</Form.Field>

		<Form.Field {config} name="after_10">
			<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
				<Form.Label class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground">
					Retry After 10 Times (hr)
				</Form.Label>
				<Form.Input type="number" step="0.01" class="text-sm md:text-base" spellcheck="false" />
			</Form.Item>
			<Form.Validation class="text-sm md:text-base text-red-500" />
		</Form.Field>

		<div class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
			<p class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground">
				Scrapers Enabled
			</p>
			<div class="flex flex-wrap gap-4">
				<Form.Field {config} name="torrentio_enabled">
					<div class="flex flex-wrap items-center gap-2">
						<Form.Checkbox />
						<Form.Label class="text-sm md:text-base">Torrentio</Form.Label>
					</div>
				</Form.Field>

				<Form.Field {config} name="orionoid_enabled">
					<div class="flex flex-wrap items-center gap-2">
						<Form.Checkbox />
						<Form.Label class="text-sm md:text-base">Orionoid</Form.Label>
					</div>
				</Form.Field>

				<Form.Field {config} name="jackett_enabled">
					<div class="flex flex-wrap items-center gap-2">
						<Form.Checkbox />
						<Form.Label class="text-sm md:text-base">Jackett</Form.Label>
					</div>
				</Form.Field>
			</div>
		</div>

		{#if $form.torrentio_enabled}
			<div transition:slide>
				<Form.Field {config} name="torrentio_filter">
					<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
						<Form.Label
							class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
						>
							Torrentio Filter
						</Form.Label>
						<Form.Input class="text-sm md:text-base" spellcheck="false" />
					</Form.Item>
					<Form.Validation class="text-sm md:text-base text-red-500" />
				</Form.Field>
			</div>
		{/if}

		{#if $form.orionoid_enabled}
			<div transition:slide>
				<Form.Field {config} name="orionoid_api_key">
					<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
						<Form.Label
							class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
						>
							Orionoid API Key
						</Form.Label>
						<Form.Input
							class={clsx('transition-all duration-300 text-sm md:text-base', {
								'blur-sm hover:blur-none focus:blur-none': $form.orionoid_api_key.length > 0
							})}
							spellcheck="false"
						/>
					</Form.Item>
					<Form.Validation class="text-sm md:text-base text-red-500" />
				</Form.Field>
			</div>
		{/if}

		{#if $form.jackett_enabled}
			<div transition:slide>
				<Form.Field {config} name="jackett_url">
					<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
						<Form.Label
							class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
						>
							Jackett URL
						</Form.Label>
						<Form.Input class="text-sm md:text-base" spellcheck="false" />
					</Form.Item>
					<Form.Validation class="text-sm md:text-base text-red-500" />
				</Form.Field>
			</div>
		{/if}

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

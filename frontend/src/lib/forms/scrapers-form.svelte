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
	import { scrapersSettingsSchema, type ScrapersSettingsSchema } from '$lib/forms/helpers';
	import { getContext } from 'svelte';
	import type { SuperValidated } from 'sveltekit-superforms';

	let formDebug: boolean = getContext('formDebug');

	export let data: SuperValidated<ScrapersSettingsSchema>;
	const scrapersForm = superForm(data);
	const { form, message, delayed, errors } = scrapersForm;

	$: if ($message && $page.status === 200) {
		toast.success($message);
	} else if ($message) {
		toast.error($message);
	}

	export let actionUrl: string = '?/default';
</script>

<Form.Root
	action={actionUrl}
	schema={scrapersSettingsSchema}
	controlled
	form={scrapersForm}
	let:config
	debug={formDebug}
>
	<div class="flex flex-col my-4 gap-4">
		<Form.Field {config} name="after_2">
			<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
				<Form.Label class="font-semibold w-48 min-w-48 text-muted-foreground">
					Retry After 2 Times (hr)
				</Form.Label>
				<Form.Input type="number" step="0.01" spellcheck="false" />
			</Form.Item>
			{#if $errors.after_2}
				<Form.Validation class="text-sm text-red-500" />
			{/if}
		</Form.Field>

		<Form.Field {config} name="after_5">
			<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
				<Form.Label class="font-semibold w-48 min-w-48 text-muted-foreground">
					Retry After 5 Times (hr)
				</Form.Label>
				<Form.Input type="number" step="0.01" spellcheck="false" />
			</Form.Item>
			{#if $errors.after_5}
				<Form.Validation class="text-sm text-red-500" />
			{/if}
		</Form.Field>

		<Form.Field {config} name="after_10">
			<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
				<Form.Label class="font-semibold w-48 min-w-48 text-muted-foreground">
					Retry After 10 Times (hr)
				</Form.Label>
				<Form.Input type="number" step="0.01" spellcheck="false" />
			</Form.Item>
			{#if $errors.after_10}
				<Form.Validation class="text-sm text-red-500" />
			{/if}
		</Form.Field>

		<div class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
			<p class="font-semibold w-48 min-w-48 text-muted-foreground">Scrapers Enabled</p>
			<div class="flex flex-wrap gap-4">
				<Form.Field {config} name="torrentio_enabled">
					<div class="flex flex-wrap items-center gap-2">
						<Form.Checkbox />
						<Form.Label>Torrentio</Form.Label>
					</div>
				</Form.Field>

				<Form.Field {config} name="orionoid_enabled">
					<div class="flex flex-wrap items-center gap-2">
						<Form.Checkbox />
						<Form.Label>Orionoid</Form.Label>
					</div>
				</Form.Field>

				<Form.Field {config} name="jackett_enabled">
					<div class="flex flex-wrap items-center gap-2">
						<Form.Checkbox />
						<Form.Label>Jackett</Form.Label>
					</div>
				</Form.Field>
			</div>
		</div>

		{#if $form.torrentio_enabled}
			<div transition:slide>
				<Form.Field {config} name="torrentio_filter">
					<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
						<Form.Label class="font-semibold w-48 min-w-48 text-muted-foreground">
							Torrentio Filter
						</Form.Label>
						<Form.Input spellcheck="false" />
					</Form.Item>
					{#if $errors.torrentio_filter}
						<Form.Validation class="text-sm text-red-500" />
					{/if}
				</Form.Field>
			</div>
		{/if}

		{#if $form.orionoid_enabled}
			<div transition:slide>
				<Form.Field {config} name="orionoid_api_key">
					<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
						<Form.Label class="font-semibold w-48 min-w-48 text-muted-foreground">
							Orionoid API Key
						</Form.Label>
						<Form.Input
							class={clsx('transition-all duration-300', {
								'blur-sm hover:blur-none focus:blur-none': $form.orionoid_api_key.length > 0
							})}
							spellcheck="false"
						/>
					</Form.Item>
					{#if $errors.orionoid_api_key}
						<Form.Validation class="text-sm text-red-500" />
					{/if}
				</Form.Field>
			</div>
		{/if}

		{#if $form.jackett_enabled}
			<div transition:slide>
				<Form.Field {config} name="jackett_url">
					<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
						<Form.Label class="font-semibold w-48 min-w-48 text-muted-foreground">
							Jackett URL
						</Form.Label>
						<Form.Input spellcheck="false" />
					</Form.Item>
					{#if $errors.jackett_url}
						<Form.Validation class="text-sm text-red-500" />
					{/if}
				</Form.Field>
			</div>
		{/if}

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
				<span class="ml-1" class:hidden={$page.url.pathname === '/settings/scrapers'}
					>and continue</span
				>
			</Button>
		</div>
	</div>
</Form.Root>

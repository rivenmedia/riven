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

	<Form.Root schema={generalSettingsSchema} controlled form={generalForm} let:config debug={false}>
		<div class="flex flex-col my-4 gap-4">
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
					<Form.Field {config} name="jackett_api_key">
						<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
							<Form.Label
								class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
							>
								Jackett API Key
							</Form.Label>
							<Form.Input
								class={clsx('transition-all duration-300 text-sm md:text-base', {
									'blur-sm hover:blur-none focus:blur-none': $form.jackett_api_key.length > 0
								})}
								spellcheck="false"
							/>
						</Form.Item>
						<Form.Validation class="text-sm md:text-base text-red-500" />
					</Form.Field>
				</div>
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
</div>

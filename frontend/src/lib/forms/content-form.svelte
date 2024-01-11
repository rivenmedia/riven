<script lang="ts">
	import { slide, fly } from 'svelte/transition';
	import { arrayProxy, superForm } from 'sveltekit-superforms/client';
	import { Button } from '$lib/components/ui/button';
	import { Separator } from '$lib/components/ui/separator';
	import { toast } from 'svelte-sonner';
	import { Loader2, X } from 'lucide-svelte';
	import { page } from '$app/stores';
	import clsx from 'clsx';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import * as Form from '$lib/components/ui/form';
	import { contentSettingsSchema, type ContentSettingsSchema } from '$lib/schemas/setting';
	import { getContext } from 'svelte';
	import type { SuperValidated } from 'sveltekit-superforms';

	let formDebug: boolean = getContext('formDebug');

	export let data: SuperValidated<ContentSettingsSchema>;
	const contentForm = superForm(data);
	const { form, message, delayed } = contentForm;

	const { values: mdblistListsValues, errors: mdblistListsErrors } = arrayProxy(
		contentForm,
		'mdblist_lists'
	);

	$: if ($message && $page.status === 200) {
		toast.success($message);
	} else if ($message) {
		toast.error($message);
	}

	let current_add_list = '';
	function addToMdblistLists(event: SubmitEvent): void {
		event.preventDefault();
		if ($mdblistListsValues.includes(current_add_list)) {
			current_add_list = '';
			toast.error('List already exists');
			return;
		}
		if (isNaN(Number(current_add_list))) {
			current_add_list = '';
			toast.error('List must be a number');
			return;
		}
		if (Number(current_add_list) <= 0) {
			current_add_list = '';
			toast.error('List must be a positive number (> 0)');
			return;
		}
		$mdblistListsValues = [...$mdblistListsValues.filter((item) => item !== ''), current_add_list];
		current_add_list = '';
	}

	function removeFromMdblistLists(list: string): void {
		$mdblistListsValues = $mdblistListsValues.filter((item) => item !== list);
		if ($mdblistListsValues.length === 0) {
			$mdblistListsValues = [''];
		}
	}
</script>

<Form.Root
	schema={contentSettingsSchema}
	controlled
	form={contentForm}
	let:config
	debug={formDebug}
>
	<div class="flex flex-col my-4 gap-4">
		<div class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
			<p class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground">
				Content Providers
			</p>
			<div class="flex flex-wrap gap-4">
				<Form.Field {config} name="overseerr_enabled">
					<div class="flex flex-wrap items-center gap-2">
						<Form.Checkbox />
						<Form.Label class="text-sm md:text-base">Overseerr</Form.Label>
					</div>
				</Form.Field>

				<Form.Field {config} name="mdblist_enabled">
					<div class="flex flex-wrap items-center gap-2">
						<Form.Checkbox />
						<Form.Label class="text-sm md:text-base">Mdblist</Form.Label>
					</div>
				</Form.Field>

				<Form.Field {config} name="plex_watchlist_enabled">
					<div class="flex flex-wrap items-center gap-2">
						<Form.Checkbox />
						<Form.Label class="text-sm md:text-base">Plex Watchlists</Form.Label>
					</div>
				</Form.Field>
			</div>
		</div>

		{#if $form.overseerr_enabled}
			<div transition:slide>
				<Form.Field {config} name="overseerr_url">
					<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
						<Form.Label
							class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
						>
							Overseerr URL
						</Form.Label>
						<Form.Input class="text-sm md:text-base" spellcheck="false" />
					</Form.Item>
					<Form.Validation class="text-sm md:text-base text-red-500" />
				</Form.Field>
			</div>

			<div transition:slide>
				<Form.Field {config} name="overseerr_api_key">
					<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
						<Form.Label
							class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
						>
							Overseerr API Key
						</Form.Label>
						<Form.Input
							class={clsx('transition-all duration-300 text-sm md:text-base', {
								'blur-sm hover:blur-none focus:blur-none': $form.overseerr_api_key.length > 0
							})}
							spellcheck="false"
						/>
					</Form.Item>
					<Form.Validation class="text-sm md:text-base text-red-500" />
				</Form.Field>
			</div>
		{/if}

		{#if $form.plex_watchlist_enabled}
			<div transition:slide>
				<Form.Field {config} name="plex_watchlist_rss">
					<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
						<Form.Label
							class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
						>
							Plex RSS URL
						</Form.Label>
						<Form.Input class="text-sm md:text-base" spellcheck="false" />
					</Form.Item>
					<Form.Validation class="text-sm md:text-base text-red-500" />
				</Form.Field>
			</div>

			<div transition:slide>
				<Form.Field {config} name="plex_watchlist_update_interval">
					<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
						<Form.Label
							class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
						>
							Plex RSS Update Interval
						</Form.Label>
						<Form.Input type="number" class="text-sm md:text-base" spellcheck="false" />
					</Form.Item>
					<Form.Validation class="text-sm md:text-base text-red-500" />
				</Form.Field>
			</div>
		{/if}

		<!--h-0 overflow-hidden instead of hidden because it prevents `required` from operating, outside of if to persist-->
		<div class="h-0 overflow-hidden">
			<select
				multiple
				id="mdblist_lists"
				name="mdblist_lists"
				bind:value={$mdblistListsValues}
				tabindex="-1"
			>
				{#each $mdblistListsValues as list}
					<option value={list}>{list}</option>
				{/each}
			</select>
		</div>

		{#if $form.mdblist_enabled}
			<div transition:slide>
				<Form.Field {config} name="mdblist_api_key">
					<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
						<Form.Label
							class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
						>
							Mdblist API Key
						</Form.Label>
						<Form.Input
							class={clsx('transition-all duration-300 text-sm md:text-base', {
								'blur-sm hover:blur-none focus:blur-none': $form.mdblist_api_key.length > 0
							})}
							spellcheck="false"
						/>
					</Form.Item>
					<Form.Validation class="text-sm md:text-base text-red-500" />
				</Form.Field>
			</div>

			<div transition:slide>
				<Form.Field {config} name="mdblist_update_interval">
					<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl">
						<Form.Label
							class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
						>
							Mdblist Update Interval
						</Form.Label>
						<Form.Input type="number" class="text-sm md:text-base" spellcheck="false" />
					</Form.Item>
					<Form.Validation class="text-sm md:text-base text-red-500" />
				</Form.Field>
			</div>

			{#if $mdblistListsErrors}
				<small class="text-sm md:text-base text-red-500">{$mdblistListsErrors}</small>
			{/if}

			<div transition:slide class="flex flex-col md:flex-row items-start max-w-6xl">
				<Label
					class="text-base md:text-lg font-semibold w-48 min-w-48 text-muted-foreground"
					for="mdblist_lists">Mdblist Lists</Label
				>
				<form on:submit={addToMdblistLists} class="w-full flex flex-col gap-4 items-start">
					<Input
						placeholder="Enter list numbers one at a time"
						class="text-sm md:text-base"
						type="number"
						bind:value={current_add_list}
					/>
					<div class="flex items-center w-full flex-wrap gap-2">
						{#each $mdblistListsValues.filter((list) => list !== '') as list (list)}
							<button
								type="button"
								in:fly={{ y: 10, duration: 200 }}
								out:fly={{ y: -10, duration: 200 }}
								class="flex items-center gap-2 py-1 px-6 text-sm bg-slate-200 dark:bg-slate-800 rounded-md"
								on:click={() => removeFromMdblistLists(list)}
							>
								<p>{list}</p>
								<X class="w-4 h-4 text-red-500" />
							</button>
						{/each}
					</div>
				</form>
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

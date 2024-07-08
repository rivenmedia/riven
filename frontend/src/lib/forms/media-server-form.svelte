<script lang="ts">
	import { slide } from 'svelte/transition';
	import { page } from '$app/stores';
	import { getContext } from 'svelte';
	import SuperDebug from 'sveltekit-superforms';
	import { zodClient } from 'sveltekit-superforms/adapters';
	import { type SuperValidated, type Infer, superForm } from 'sveltekit-superforms';
	import * as Form from '$lib/components/ui/form';
	import { mediaServerSettingsSchema, type MediaServerSettingsSchema } from '$lib/forms/helpers';
	import { toast } from 'svelte-sonner';
	import TextField from './components/text-field.svelte';
	import NumberField from './components/number-field.svelte';
	import { Loader2 } from 'lucide-svelte';
	import { Separator } from '$lib/components/ui/separator';
	import { v4 as uuidv4 } from 'uuid';
	import { Button } from '$lib/components/ui/button';
	import CheckboxField from './components/checkbox-field.svelte';
	import GroupCheckboxField from './components/group-checkbox-field.svelte';

	export let data: SuperValidated<Infer<MediaServerSettingsSchema>>;
	export let actionUrl: string = '?/default';

	const formDebug: boolean = getContext('formDebug');

	const form = superForm(data, {
		validators: zodClient(mediaServerSettingsSchema)
	});

	const { form: formData, enhance, message, errors, delayed } = form;

	$: if ($message && $page.status === 200) {
		toast.success($message);
	} else if ($message) {
		toast.error($message);
	}

	let ongoingAuth: boolean = false;
	let clientIdentifier: string;
	let genClientIdentifier = () => {
		clientIdentifier = uuidv4();
		return clientIdentifier;
	};
	let appName = 'Riven';
	let plexId: string;
	let plexCode: string;
	let pollingInterval: any;

	async function genPlexPin() {
		let data = await fetch('https://plex.tv/api/v2/pins?strong=true', {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				Accept: 'application/json',
				'X-Plex-Product': appName,
				code: plexCode,
				'X-Plex-Client-Identifier': genClientIdentifier()
			}
		});

		return await data.json();
	}

	async function pollPlexPin() {
		let data = await fetch(`https://plex.tv/api/v2/pins/${plexId}`, {
			method: 'GET',
			headers: {
				'Content-Type': 'application/json',
				Accept: 'application/json',
				'X-Plex-Product': appName,
				'X-Plex-Client-Identifier': clientIdentifier
			}
		});

		let json = await data.json();
		if ('errors' in json) {
			toast.error(json.errors[0].message);
			ongoingAuth = false;
			clearInterval(pollingInterval);
		}

		if (json.authToken) {
			$formData.plex_token = json.authToken;
			clearInterval(pollingInterval);
			ongoingAuth = false;
		}
	}

	async function startLogin(): Promise<void> {
		ongoingAuth = true;
		try {
			const pin = await genPlexPin();
			if ('errors' in pin) {
				toast.error(pin.errors[0].message);
				ongoingAuth = false;
				return;
			}
			plexId = pin.id;
			plexCode = pin.code;

			window.open(
				`https://app.plex.tv/auth#?clientID=${clientIdentifier}&code=${plexCode}&context%5Bdevice%5D%5Bproduct%5D=${appName}`
			);

			pollingInterval = setInterval(pollPlexPin, 2000);
		} catch (e) {
			console.error(e);
		}
	}
</script>

<form method="POST" action={actionUrl} use:enhance class="my-8 flex flex-col gap-2">
	<NumberField {form} name="update_interval" {formData} stepValue={1} />

	<GroupCheckboxField
		fieldTitle="Updaters"
		fieldDescription="Choose the updater services you want to enable"
	>
		<CheckboxField {form} name="local_enabled" label="Local Updater" {formData} isForGroup={true} />
		<CheckboxField {form} name="plex_enabled" label="Plex Updater" {formData} isForGroup={true} />
	</GroupCheckboxField>

	{#if $formData.plex_enabled}
		<div transition:slide>
			<TextField {form} name="plex_url" {formData} label="Plex URL" />
		</div>

		<div transition:slide>
			<Form.Field {form} name="plex_token">
				<Form.Control let:attrs>
					<div class="mb-2 flex max-w-6xl flex-col items-start gap-2 md:flex-row md:gap-4">
						<div class="flex w-full min-w-48 flex-col items-start gap-2 md:w-48">
							<Form.Label>Plex Token</Form.Label>
							<p class="text-muted-foreground text-xs">
								Click the button to generate a new Plex token
							</p>
						</div>
						<input type="hidden" name="plex_token" id="plex_token" value={$formData.plex_token} />
						<Button
							type="button"
							disabled={ongoingAuth}
							variant="outline"
							size="sm"
							class="w-full"
							on:click={async () => {
								await startLogin();
							}}
						>
							{#if ongoingAuth}
								<Loader2 class="mr-2 h-4 w-4 animate-spin" />
							{/if}
							{#if $formData.plex_token.length > 0}
								<p class="w-full text-left">
									Reauthenticate with Plex
									<span class="ml-1">({$formData.plex_token.slice(0, 5)}...)</span>
								</p>
							{:else}
								<p class="w-full text-left">Authenticate with Plex</p>
							{/if}
						</Button>
					</div>
				</Form.Control>
			</Form.Field>
		</div>
	{/if}

	<Separator class="mt-4" />
	<div class="flex w-full justify-end">
		<Form.Button disabled={$delayed} type="submit" size="sm" class="w-full lg:max-w-max">
			{#if $delayed}
				<Loader2 class="mr-2 h-4 w-4 animate-spin" />
			{/if}
			Save changes
			<span class="ml-1" class:hidden={$page.url.pathname === '/settings/mediaserver'}
				>and continue</span
			>
		</Form.Button>
	</div>
</form>

{#if formDebug}
	<SuperDebug data={$formData} />
{/if}

<script lang="ts">
	import { superForm } from 'sveltekit-superforms/client';
	import { Button } from '$lib/components/ui/button';
	import { Separator } from '$lib/components/ui/separator';
	import { toast } from 'svelte-sonner';
	import { Loader2 } from 'lucide-svelte';
	import { page } from '$app/stores';
	import * as Form from '$lib/components/ui/form';
	import { mediaServerSettingsSchema, type MediaServerSettingsSchema } from '$lib/forms/helpers';
	import { getContext } from 'svelte';
	import type { SuperValidated } from 'sveltekit-superforms';
	import { v4 as uuidv4 } from 'uuid';
	import FormTextField from './components/form-text-field.svelte';

	let formDebug: boolean = getContext('formDebug');

	export let data: SuperValidated<MediaServerSettingsSchema>;
	const mediaServerForm = superForm(data);
	const { form, message, delayed, errors } = mediaServerForm;

	$: if ($message && $page.status === 200) {
		toast.success($message);
	} else if ($message) {
		toast.error($message);
	}

	export let actionUrl: string = '?/default';

	let ongoingAuth: boolean = false;
	let clientIdentifier: string;
	let genClientIdentifier = () => {
		clientIdentifier = uuidv4();
		return clientIdentifier;
	};
	let appName = 'Iceberg';
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
			$form.plex_token = json.authToken;
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

<Form.Root
	action={actionUrl}
	schema={mediaServerSettingsSchema}
	controlled
	form={mediaServerForm}
	let:config
	debug={formDebug}
>
	<div class="flex flex-col my-4 gap-4">
		<FormTextField {config} fieldName="plex_url" labelName="Plex URL" errors={$errors.plex_url} />

		<Form.Field {config} name="plex_token">
			<Form.Item class="flex flex-col md:flex-row items-start md:items-center max-w-6xl md:gap-4">
				<Form.Label class="font-semibold w-48 min-w-48">
					Plex Token
				</Form.Label>
				<input type="hidden" name="plex_token" id="plex_token" value={$form.plex_token} />
				<Button
					on:click={async () => {
						await startLogin();
					}}
					disabled={ongoingAuth}
					size="sm"
					variant="secondary"
					class="w-full md:max-w-max text-xs font-semibold"
				>
					{#if ongoingAuth}
						<Loader2 class="w-4 h-4 animate-spin mr-2" />
					{/if}
					{#if $form.plex_token.length > 0}
						Reauthenticate with Plex
					{:else}
						Authenticate with Plex
					{/if}
				</Button>
			</Form.Item>
			{#if $errors.plex_token}
				<Form.Validation class="text-sm text-red-500" />
			{/if}
		</Form.Field>

		<Separator class=" mt-4" />
		<div class="flex w-full justify-end">
			<Button
				disabled={$delayed}
				type="submit"
				size="sm"
				class="w-full md:max-w-max text-xs font-semibold"
			>
				{#if $delayed}
					<Loader2 class="w-4 h-4 animate-spin mr-2" />
				{/if}
				Save changes
				<span class="ml-1" class:hidden={$page.url.pathname === '/settings/mediaserver'}
					>and continue</span
				>
			</Button>
		</div>
	</div>
</Form.Root>

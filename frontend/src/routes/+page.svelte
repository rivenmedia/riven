<script lang="ts">
	import type { PageData } from './$types';
	import { Separator } from '$lib/components/ui/separator';
	import { Loader2, Check, X, CircleDot, Download, Mail, Calendar } from 'lucide-svelte';
	import ServiceStatus from '$lib/components/service-status.svelte';
	import { formatDate, formatRDDate } from '$lib/helpers';
	import * as Card from '$lib/components/ui/card';

	export let data: PageData;
</script>

<svelte:head>
	<title>Iceberg | Home</title>
</svelte:head>

<div class="flex w-full flex-col p-8 font-medium md:px-24 lg:px-32">
	{#if data.appData.user.success}
		<div class="grid grid-flow-row gap-4 lg:grid-flow-col">
			<Card.Root class="min-h-96">
				<Card.Header class="flex flex-col items-center border-b">
					<Card.Title>Recently Requested</Card.Title>
					<Card.Description>Items you requested recently</Card.Description>
				</Card.Header>
				<Card.Content class="mt-4 flex flex-col items-start gap-4">
					Soon..
				</Card.Content>
			</Card.Root>

			<Card.Root>
				<Card.Header class="flex flex-col items-center border-b">
					<Card.Title>Services</Card.Title>
					<Card.Description>Know the status of services</Card.Description>
				</Card.Header>
				<Card.Content class="mt-4 flex flex-col items-start gap-4">
					<ServiceStatus data={data.appData.services.data} />
				</Card.Content>
			</Card.Root>

			<Card.Root>
				<Card.Header class="flex flex-col items-center border-b">
					<Card.Title>Account information</Card.Title>
					<Card.Description>Information about your account</Card.Description>
				</Card.Header>
				<Card.Content class="mt-4 flex flex-col items-start gap-4">
					<div class="flex items-center gap-2">
						<div class="bg-secondary rounded-full p-2">
							<Download class="h-6 w-6 p-1" />
						</div>
						<div class="flex flex-col items-start">
							<p>Dowloader configured</p>
							{#if data.appData.downloader === 'rd'}
								<p class="text-muted-foreground text-sm">Real-Debrid</p>
							{:else}
								<p class="text-muted-foreground text-sm">Torbox</p>
							{/if}
						</div>
					</div>

					<div class="flex items-center gap-2">
						<div class="bg-secondary rounded-full p-2">
							<Mail class="h-6 w-6 p-1" />
						</div>
						<div class="flex flex-col items-start">
							<p>Email Address</p>
							<p class="text-muted-foreground text-sm">{data.appData.user.data.email}</p>
						</div>
					</div>

					<div class="flex items-center gap-2">
						<div class="bg-secondary rounded-full p-2">
							<Calendar class="h-6 w-6 p-1" />
						</div>
						<div class="flex flex-col items-start">
							<p>Subscription</p>
							{#if data.appData.downloader === 'rd'}
								<p class="text-muted-foreground text-sm">
									Expires on {formatRDDate(data.appData.user.data.expiration, 'short')} ({formatRDDate(
										data.appData.user.data.expiration,
										'left'
									)})
								</p>
							{:else}
								<p class="text-muted-foreground text-sm">
									Expires on {formatDate(data.appData.user.data.premium_expires_at, 'short')} ({formatDate(
										data.appData.user.data.premium_expires_at,
										'left'
									)})
								</p>
							{/if}
						</div>
					</div>
				</Card.Content>
			</Card.Root>
		</div>
	{/if}
</div>

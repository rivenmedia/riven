<script lang="ts">
	import type { PageData } from './$types';
	import * as Carousel from '$lib/components/ui/carousel/index.js';

	export let data: PageData;
</script>

<svelte:head>
	<title>Iceberg | Home</title>
</svelte:head>

<div class="flex w-full flex-col">
	<Carousel.Root class="w-full h-[50vh] md:h-[100vh]">
		<Carousel.Content>
			<!-- <Carousel.Item>...</Carousel.Item>
			<Carousel.Item>...</Carousel.Item>
			<Carousel.Item>...</Carousel.Item> -->
			{#each data.nowPlaying.data.results as nowPlaying}
				<Carousel.Item class="w-full">
					<img class="w-full" src="https://www.themoviedb.org/t/p/w1280{nowPlaying.backdrop_path}" alt="{nowPlaying.title}" />
				</Carousel.Item>
			{/each}
		</Carousel.Content>
	</Carousel.Root>
</div>

<!-- <div class="flex w-full flex-col p-8 font-medium md:px-24 lg:px-32 pt-16">
	{#if data.appData.user.success}
		<div class="grid grid-flow-row gap-4 lg:grid-flow-col">
			<Card.Root class="min-h-96">
				<Card.Header class="flex flex-col items-center border-b">
					<Card.Title>Recently Requested</Card.Title>
					<Card.Description>Items you requested recently</Card.Description>
				</Card.Header>
				<Card.Content class="mt-4 flex flex-col items-start gap-4">Soon..</Card.Content>
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
						<div class="rounded-full bg-secondary p-2">
							<Download class="h-6 w-6 p-1" />
						</div>
						<div class="flex flex-col items-start">
							<p>Dowloader configured</p>
							{#if data.appData.downloader === 'rd'}
								<p class="text-sm text-muted-foreground">Real-Debrid</p>
							{:else}
								<p class="text-sm text-muted-foreground">Torbox</p>
							{/if}
						</div>
					</div>

					<div class="flex items-center gap-2">
						<div class="rounded-full bg-secondary p-2">
							<Mail class="h-6 w-6 p-1" />
						</div>
						<div class="flex flex-col items-start">
							<p>Email Address</p>
							<p class="text-sm text-muted-foreground">{data.appData.user.data.email}</p>
						</div>
					</div>

					<div class="flex items-center gap-2">
						<div class="rounded-full bg-secondary p-2">
							<Calendar class="h-6 w-6 p-1" />
						</div>
						<div class="flex flex-col items-start">
							<p>Subscription</p>
							{#if data.appData.downloader === 'rd'}
								<p class="text-sm text-muted-foreground">
									Expires on {formatRDDate(data.appData.user.data.expiration, 'short')} ({formatRDDate(
										data.appData.user.data.expiration,
										'left'
									)})
								</p>
							{:else}
								<p class="text-sm text-muted-foreground">
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
</div> -->

<script lang="ts">
	import type { PageData } from './$types';
	import * as Carousel from '$lib/components/ui/carousel/index.js';
	import Autoplay from 'embla-carousel-autoplay';
	import Header from '$lib/components/header.svelte';
	import {
		Star,
		CalendarDays,
		Languages,
		Play,
		Info,
		Flame,
		Clapperboard,
		Tv,
		Sparkle,
		MoveUpRight
	} from 'lucide-svelte';
	import { Button } from '$lib/components/ui/button';
	import { roundOff } from '$lib/helpers';

	export let data: PageData;
</script>

<svelte:head>
	<title>Riven | Home</title>
</svelte:head>

<Carousel.Root
	plugins={[
		Autoplay({
			delay: 5000
		})
	]}
	class="h-[100dvh] overflow-hidden"
>
	<div class="absolute top-0 z-50 w-full">
		<Header />
	</div>
	<Carousel.Content class="h-full">
		{#each data.nowPlaying.data.results as nowPlaying, i}
			{#if i <= 9}
				<Carousel.Item class="h-full w-full min-w-full basis-full pl-0 text-slate-50">
					<div class="relative">
						<img
							src="https://www.themoviedb.org/t/p/original{nowPlaying.backdrop_path}"
							alt={nowPlaying.title}
							class="h-[100dvh] w-full translate-y-[calc(50dvh-50%)] select-none object-cover object-center"
							loading="lazy"
						/>
						<div class="absolute inset-0 z-[1] flex select-none bg-slate-900 opacity-60"></div>
						<div class="absolute inset-0 z-[2] mt-16 flex flex-col gap-4 md:mb-56">
							<!-- TODO: Maybe change m-4 to padding? -->
							<div class="ml-4 flex h-full w-full flex-col justify-end gap-2 p-8 md:px-24 lg:px-32">
								<div class="w-full max-w-2xl select-none">
									<h1 class="break-words text-3xl font-semibold leading-tight md:text-4xl">
										{nowPlaying.title}
									</h1>
								</div>
								<div class="flex flex-wrap items-center gap-2 text-xs text-zinc-200">
									<div class="flex items-center gap-2">
										<Star class="size-4" />
										<p>{roundOff(nowPlaying.vote_average)}</p>
									</div>
									<div class="flex items-center gap-2">
										<CalendarDays class="size-4" />
										<p>{nowPlaying.release_date}</p>
									</div>
									<div class="flex items-center gap-2 uppercase">
										<Languages class="size-4" />
										<p>{nowPlaying.original_language}</p>
									</div>
								</div>
								<div class="mt-2 w-full max-w-2xl select-none">
									<p class="line-clamp-2 text-base">{nowPlaying.overview}</p>
								</div>
								<div class="mt-2 flex gap-2">
									<Button
										size="lg"
										variant="default"
										class="flex items-center gap-2"
										href={`/movie/${nowPlaying.id}`}
									>
										<Play class="h-4 w-4" />
										<span>Request</span>
									</Button>
									<Button
										size="lg"
										variant="ghost"
										class="flex items-center gap-2"
										href={`/movie/${nowPlaying.id}`}
									>
										<Info class="h-4 w-4" />
										<span>Details</span>
									</Button>
								</div>
							</div>
						</div>
					</div>
				</Carousel.Item>
			{/if}
		{/each}
	</Carousel.Content>
</Carousel.Root>

<div class="flex w-full flex-col items-start gap-4 p-8 md:-mt-56">
	<div class="z-50 flex w-full items-center gap-4 md:px-16 lg:px-24">
		<div class="rounded-md bg-red-400 p-2 text-white">
			<Flame class="size-4" />
		</div>
		<h2 class="text-xl font-semibold md:text-2xl">What's Trending Today</h2>
	</div>
	<Carousel.Root
		opts={{
			dragFree: true
		}}
		plugins={[
			Autoplay({
				delay: 5000
			})
		]}
		class="w-full overflow-hidden"
	>
		<Carousel.Content class="w-full">
			{#each data.trendingAll.data.results as trendingAll, i}
				{#if trendingAll.media_type !== 'person'}
					<Carousel.Item class="basis-auto text-slate-50">
						<div
							class="hover:border-primary aspect-[2/1] h-fit w-full overflow-hidden rounded-2xl border-2 border-transparent hover:border-2"
						>
							<a
								href={`/movie/${trendingAll.id}`}
								class="group relative flex h-full w-full flex-shrink-0 flex-col"
							>
								<div class="z-0">
									<span
										><img
											src="https://image.tmdb.org/t/p/w342{trendingAll.backdrop_path}"
											alt={trendingAll.name}
											class="size-full object-cover object-center transition-all duration-300 ease-in-out group-hover:scale-105"
										/></span
									>
								</div>
								<div class="absolute inset-0 z-[1] flex select-none bg-slate-900 opacity-20"></div>
								<div class="absolute inset-0 z-[2] flex flex-col justify-end gap-2 p-4">
									<div class="flex items-center gap-2">
										<Clapperboard class="size-4" />
										<p class="line-clamp-1">{trendingAll.name || trendingAll.original_title}</p>
									</div>
									<div class="text-primary-foreground flex items-center gap-2 text-xs">
										<div class="flex items-center gap-2">
											<Star class="size-4" />
											<p>{roundOff(trendingAll.vote_average)}</p>
										</div>
										<div class="flex items-center gap-2">
											<CalendarDays class="size-4" />
											<p>{trendingAll.release_date || trendingAll.first_air_date}</p>
										</div>
										<div class="flex items-center gap-2 uppercase">
											<Languages class="size-4" />
											<p>{trendingAll.original_language}</p>
										</div>
									</div>
								</div>
							</a>
						</div>
					</Carousel.Item>
				{/if}
			{/each}
		</Carousel.Content>
	</Carousel.Root>
</div>

<div class="flex h-full w-full flex-col p-8 md:px-24 lg:px-32">
	<div class="mx-auto flex w-full flex-col gap-4 xl:flex-row">
		<div class="my-2 flex flex-col gap-3 md:my-0 md:gap-4 xl:w-[70%]">
			<div class="flex items-center justify-between">
				<div class="flex items-center gap-2">
					<div class="bg-primary rounded-md p-2 text-white">
						<Clapperboard class="size-4" />
					</div>
					<h2 class="text-xl font-semibold md:text-2xl">Movies</h2>
				</div>
				<a href="/movies" class="text-primary-foreground flex items-center gap-2">
					<span>View All</span>
					<MoveUpRight class="size-4" />
				</a>
			</div>

			<div class="no-scrollbar flex flex-wrap overflow-x-auto px-1 lg:p-0">
				{#each data.trendingMovies.data.results as trendingMovies, i}
					<!-- {#if i <= 17} -->
					<a
						href={`/movie/${trendingMovies.id}`}
						class="group relative mb-2 flex w-1/2 flex-shrink-0 flex-col gap-2 rounded-lg p-2 sm:w-1/4 lg:w-1/6 xl:p-[.4rem]"
					>
						<div class="relative aspect-[1/1.5] w-full overflow-hidden rounded-lg">
							<img
								src="https://image.tmdb.org/t/p/w342{trendingMovies.poster_path}"
								alt={trendingMovies.title}
								class="h-full w-full object-cover object-center transition-all duration-300 ease-in-out group-hover:scale-105"
							/>
							<div
								class="absolute right-0 top-1 flex items-center justify-center gap-1 rounded-l-md bg-slate-900/70 px-[5px] py-1"
							>
								<Star class="size-3 text-yellow-400" />
								<span class="text-xs font-light">
									{roundOff(trendingMovies.vote_average)}
								</span>
							</div>
						</div>
					</a>
					<!-- {/if} -->
				{/each}
			</div>
		</div>

		<div class="mt-0 hidden h-full flex-col gap-3 px-1 md:gap-4 lg:w-[30%] xl:flex overflow-y-hidden w-full">
			<div class="flex items-center justify-between">
				<div class="flex items-center gap-2">
					<div class="bg-primary rounded-md p-2 text-white">
						<Star class="size-4" />
					</div>
					<h2 class="text-xl font-semibold md:text-2xl">Top Movies</h2>
				</div>
				<a href="/movies" class="text-primary-foreground flex items-center gap-2">
					<span>View All</span>
					<MoveUpRight class="size-4" />
				</a>
			</div>
			<div class="flex flex-col gap-2 overflow-hidden">
				{#each data.moviesPopular.data.results as moviesPopular, i}
					{#if i <= 9}
						<a
							class="group flex aspect-[4.3/1] w-full gap-1 overflow-hidden rounded-lg 2xl:aspect-[5.33/1]"
							href={`/movie/${moviesPopular.id}`}
						>
							<div class="aspect-[1/1.2] h-full overflow-hidden rounded-md">
								<img
									src={`https://image.tmdb.org/t/p/w342${moviesPopular.poster_path}`}
									alt={moviesPopular.title}
									class="h-full w-full object-cover object-center transition-all duration-300 ease-in-out group-hover:scale-105"
								/>
							</div>
							<div class="flex h-full w-full flex-col gap-1 p-2">
								<h3 class="line-clamp-2 w-full text-base leading-snug">{moviesPopular.title}</h3>
								<div class="flex items-center gap-2 text-xs font-normal">
									<div class="flex items-center gap-1">
										<CalendarDays class="size-4 text-muted-foreground" />
										<p>{moviesPopular.release_date}</p>
									</div>
									<div class="flex items-center gap-1">
										<Star class="size-4 text-muted-foreground" />
										<p>{roundOff(moviesPopular.vote_average)}</p>
									</div>
								</div>
							</div>
						</a>
					{/if}
				{/each}
			</div>
		</div>
	</div>
</div>

<style>
	.no-scrollbar::-webkit-scrollbar {
		display: none;
	}
</style>

<script lang="ts">
    import type { PageData } from './$types';
    import GeneralForm from '$lib/forms/general-form.svelte';
    
    export let data: PageData;
</script>

<GeneralForm data={data.form} />
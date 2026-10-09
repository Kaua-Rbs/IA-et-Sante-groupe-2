<script lang="ts">
	interface Props {
		form?: { error?: string; reasons?: string[]; success?: string } | null;
	}

	let { form = null }: Props = $props();
</script>

{#if form?.error}
	<div class="alert alert--error" role="alert">
		{form.error}
		{#if form.reasons?.length}
			<ul>
				{#each form.reasons as reason}
					<li>{reason}</li>
				{/each}
			</ul>
		{/if}
	</div>
{:else if form?.success}
	<div class="alert alert--success" role="status">{form.success}</div>
{/if}

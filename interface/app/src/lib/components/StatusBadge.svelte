<script lang="ts">
	interface Props {
		status: string;
		labels: Record<string, string>;
	}

	let { status, labels }: Props = $props();
</script>

<span class="badge badge--{status}">{labels[status] ?? status}</span>

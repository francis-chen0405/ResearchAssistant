import type {
  ModelUsageCostBasis,
  UsageTokenCount,
  RunSnapshot,
} from "@/lib/api";

export function formatUsageTokenCount(value: UsageTokenCount): string {
  if (value.total != null)
    return `${value.total.toLocaleString()}${value.complete ? "" : " reported; total incomplete"}`;
  if (value.known_subtotal > 0)
    return `at least ${value.known_subtotal.toLocaleString()} known; total incomplete`;
  return value.complete ? "0" : "unavailable; total incomplete";
}

export function costBasisLabel(basis: ModelUsageCostBasis | null): string {
  if (basis === "published_cache_prices_reported_writes")
    return "published cache prices and reported cache-write tokens";
  if (basis === "published_cache_prices_assumed_all_uncached_writes")
    return "published cache prices; all uncached input assumed to incur cache-write charges";
  if (basis === "configured_price_cap") return "configured price cap";
  return "pricing basis not recorded";
}

export function ModelUsageDisclosure({ snapshot }: { snapshot: RunSnapshot }) {
  const usage = snapshot.model_usage_details;
  if (!usage)
    return (
      <p className="usage-details-unavailable">
        Token-level usage detail is unavailable for this saved run.
      </p>
    );
  return (
    <details className="model-usage-details">
      <summary>Recorded token usage and cost basis</summary>
      <dl>
        <div>
          <dt>Input tokens</dt>
          <dd>{formatUsageTokenCount(usage.input_tokens)}</dd>
        </div>
        <div>
          <dt>Output tokens</dt>
          <dd>{formatUsageTokenCount(usage.output_tokens)}</dd>
        </div>
        <div>
          <dt>Cached input tokens</dt>
          <dd>{formatUsageTokenCount(usage.cached_input_tokens)}</dd>
        </div>
        <div>
          <dt>Cache-write tokens</dt>
          <dd>{formatUsageTokenCount(usage.cache_write_tokens)}</dd>
        </div>
      </dl>
      <p>
        <strong>Estimated cost basis:</strong>{" "}
        {usage.cost_basis_counts.length
          ? usage.cost_basis_counts
              .map(
                (item) =>
                  `${item.physical_calls} call${item.physical_calls === 1 ? "" : "s"}: ${costBasisLabel(item.basis)}`,
              )
              .join(" · ")
          : "No cost-basis detail was recorded."}
      </p>
      <small>
        These are provider-reported usage details and estimates, not an invoice.
      </small>
    </details>
  );
}

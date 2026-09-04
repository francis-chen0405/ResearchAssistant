import type { HostedHistoryItem } from "@/lib/hosted-api";

type Props = { items: HostedHistoryItem[]; onSelect: (id: string) => void };

export function HistoryView({ items, onSelect }: Props): React.ReactElement {
  return <section className="history-view"><p className="eyebrow">Your research archive</p><h2>Questions you’ve already asked.</h2><p className="muted intro-copy">Every run keeps its claim, status, checkpoints, and release artifacts available to your account.</p>{items.length ? <div className="history-table">{items.map((item) => <button key={item.run_id} type="button" onClick={() => onSelect(item.run_id)}><span className="history-state">{item.status}</span><strong>{item.raw_claim}</strong><time dateTime={item.updated_at}>{new Date(item.updated_at).toLocaleDateString()}</time><span className="arrow">→</span></button>)}</div> : <div className="empty-state"><h3>Your archive is quiet.</h3><p className="muted">Start a question and it will appear here.</p></div>}</section>;
}

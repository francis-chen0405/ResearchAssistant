import { useState } from "react";
import { Button } from "@/components/ui";
import { Dialog } from "@/components/dialog";
import { Icon } from "@/components/icons";
import findings from "./example-findings.json";

const ecology = findings[3];
const samples = [
  { topic: "Ecology", title: "Biodiversity loss increases risk of extinction", meta: "November 6, 2026 · Support-only search", finding: ecology.finding,
    publisher: "News-Medical", kind: "Secondary reporting", source: ecology.title, passage: ecology.passage.split("\n\n")[1], highlight: 'when other species are not present to fill the "gap" created by the loss of a species', url: ecology.url },
  { topic: "Transit", title: "Buses got faster on Manhattan’s 14th Street.", meta: "Urban transportation", finding: "After the busway opened, the city reported speed gains of up to 24%. That figure describes the largest improvement on this corridor.",
    publisher: "NYC DOT", kind: "Agency report", source: "Manhattan’s 14th Street busway, in numbers", passage: "Since busway was installed, bus speeds have increased as much as 24 percent, with ridership up as much as 30 percent", highlight: "bus speeds have increased as much as 24 percent", url: "https://www.nyc.gov/html/dot/html/pr2026/kick-off-transformation-manhattan-14-street.shtml" },
  { topic: "Space", title: "Europa may have an ocean beneath its ice.", meta: "Planetary science", finding: "Galileo measured a magnetic response that a layer of salt water beneath the ice could explain.",
    publisher: "NASA", kind: "Mission science", source: "What Galileo measured near Europa", passage: "scientists think the most likely material to create this magnetic signature is a global ocean of salty water", highlight: "a global ocean of salty water", url: "https://science.nasa.gov/jupiter/jupiter-moons/europa/europa-facts/" },
];

export function HomeView({ onResearch }: { onResearch: () => void }) {
  const [index, setIndex] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const [paused, setPaused] = useState(false);
  const [detail, setDetail] = useState<"report" | "source" | null>(null);
  const sample = samples[index];
  const [before, after] = sample.passage.split(sample.highlight);
  function select(next: number) {
    setIndex(next);
    setExpanded(false);
  }
  return (
    <section className="home landing">
      <div className="hero-copy">
        <h1>Trace a claim<br />to its <em>source.</em></h1>
        <Button variant="primary" icon="plus" onClick={onResearch}>Start research</Button>
      </div>
      <section className="sample-deck" aria-label="Research examples" aria-roledescription="carousel" data-paused={paused || expanded || detail !== null}>
        <div className="arrangement" data-topic={index} key={index} role="group" aria-label={sample.topic}>
          <div className="printing" aria-hidden="true"><span>[{index + 1}]</span></div>
          <article className="folio">
            <div className="folio-top"><span>{index === 0 ? "Example report" : "Illustrative example"}</span>
              {index === 0 && <button onClick={() => setDetail("report")}>Open report</button>}
            </div>
            <h2>{sample.title}</h2><p className="folio-meta">{sample.meta}</p><div className="folio-rule" />
            <button className="sample-finding" aria-expanded={expanded} aria-controls="sample-clipping" onClick={() => setExpanded(!expanded)}>
              {sample.finding}<small>{expanded ? "Hide exact passage" : "Read exact passage"} ↗</small>
            </button>
          </article>
          <aside id="sample-clipping" className="clipping" key={String(expanded)}>
            <div className="clip-byline"><strong>{sample.publisher}</strong><span>{sample.kind}</span></div>
            {expanded ? <><blockquote>{before}<mark>{sample.highlight}</mark>{after}</blockquote>
              {index === 0 ? <button onClick={() => setDetail("source")}>Publication and context</button> : <a href={sample.url} target="_blank" rel="noreferrer">Read publication ↗</a>}
            </> : <p>{sample.source}</p>}
          </aside>
        </div>
        <div className="sample-controls">
          {samples.map((s, i) => <button key={s.topic} aria-pressed={index === i} onClick={() => select(i)}>{s.topic}
            <i aria-hidden="true">{i === index && <b onAnimationEnd={() => select((index + 1) % samples.length)} />}</i>
          </button>)}
          <button className="play-toggle" aria-label={paused ? "Play examples" : "Pause examples"} onClick={() => setPaused(!paused)}>{paused ? "▶" : "Ⅱ"}</button>
        </div>
      </section>
      {detail && <Dialog title={detail === "report" ? samples[0].title : ecology.title} onClose={() => setDetail(null)} wide>
        <div className="sample-report">
          {detail === "report" && <><p>November 6, 2026 · Support-only search</p><h3>Conclusion</h3><p>Species loss can trigger further extinctions when other species cannot fill the missing ecological role. The broader claim remains open.</p>
            <h3>Coverage</h3><p>Six sources supported the claim and nine added context. One research question remained unresolved. The search did not examine opposing evidence.</p><h3>Findings</h3></>}
          {(detail === "report" ? findings : [ecology]).map(item => <details key={item.url + item.finding} open={detail === "source"}>
            <summary>{item.finding}</summary><h4>{item.title}</h4><blockquote>{item.passage}</blockquote>
            <a href={item.url} target="_blank" rel="noreferrer">Open publication <Icon name="arrowRight" size={14} /></a>
            {item.limitations.length > 0 && <><h4>Limitations</h4><ul>{item.limitations.map(l => <li key={l}>{l}</li>)}</ul></>}
          </details>)}
        </div>
      </Dialog>}
    </section>
  );
}

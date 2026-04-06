interface Advantage {
  label: string;
  tooltip: string;
  cls: string;
}

interface Props {
  advantages: Advantage[];
}

export default function PlayerAdvantages({ advantages }: Props) {
  if (advantages.length === 0) return null;
  return (
    <div className="advantages-bar">
      {advantages.map((a, i) => (
        <span key={i} className={`advantage-chip ${a.cls}`} data-tooltip={a.tooltip}>
          {a.label}
        </span>
      ))}
    </div>
  );
}

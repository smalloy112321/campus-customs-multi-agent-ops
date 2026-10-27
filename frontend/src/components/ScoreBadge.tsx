export const ratingClass = (rating: string) =>
  rating === 'Efficient' ? 'good' : rating === 'Acceptable' ? 'warn' : 'bad'

export default function ScoreBadge({ score, rating }: { score: number; rating: string }) {
  return (
    <span className={`score-badge score-${ratingClass(rating)}`} title={`Efficiency ${score}/100 · ${rating}`}>
      <span aria-hidden="true">⚡</span> {score}
      <span className="sr-only"> out of 100, {rating}</span>
    </span>
  )
}

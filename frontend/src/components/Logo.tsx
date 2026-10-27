// Campus Customs felt-pennant logo (EST. 1975), drawn inline so it uses the bundled Graduate font.

const FONT = "'Graduate', Georgia, serif"
const CREAM = '#F6F1E6'
const NAVY = '#00356B'
const SHADOW = '#6C8EBF'

function Lettering({ text, y, size, width }: { text: string; y: number; size: number; width: number }) {
  // A light-blue copy offset behind the cream letters gives a vintage screen-print look.
  // textLength locks the width so the words always stay inside the stitch line.
  const common = {
    textAnchor: 'middle' as const,
    textLength: width,
    lengthAdjust: 'spacingAndGlyphs' as const,
    fontFamily: FONT,
    fontSize: size,
  }
  return (
    <>
      <text x={117} y={y + 1.2} fill={SHADOW} {...common}>{text}</text>
      <text x={116} y={y} fill={CREAM} {...common}>{text}</text>
    </>
  )
}

export default function Logo({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="28 40 274 120" role="img" aria-labelledby="logo-title">
      <title id="logo-title">Campus Customs, established 1975</title>
      <polygon points="30,42 300,100 30,158" fill={NAVY} />
      <rect x="30" y="42" width="26" height="116" fill={CREAM} stroke={NAVY} strokeWidth="2" />
      <polyline points="62,52 282,100 62,148" fill="none" stroke={CREAM} strokeWidth="1.2" strokeDasharray="4 3" />
      <text
        x="43"
        y="100"
        textAnchor="middle"
        dominantBaseline="middle"
        transform="rotate(-90 43 100)"
        fontFamily={FONT}
        fontSize="12"
        fill={NAVY}
        letterSpacing="1.5"
      >
        EST. 1975
      </text>
      <Lettering text="CAMPUS" y={98} size={22} width={92} />
      <Lettering text="CUSTOMS" y={119} size={15} width={80} />
    </svg>
  )
}

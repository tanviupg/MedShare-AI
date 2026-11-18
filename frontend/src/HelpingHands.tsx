export function HelpingHands() {
  return <svg className="ml-helping-hands" viewBox="0 0 640 380" role="img" aria-label="Helping hands passing medicine from a donor through a clinic to a patient">
    <defs><pattern id="ml-pencil" width="7" height="7" patternUnits="userSpaceOnUse"><path d="M0 7L7 0" className="ml-pencil-line" /></pattern></defs>
    <path className="ml-art-sage" d="M136 310C33 255 40 141 124 112c66-23 76-68 159-61 98 8 118 48 184 72 96 35 131 123 59 191-58 55-121 7-185 15-70 10-137 19-205-19Z" />
    <path className="ml-art-outline ml-journey-path" d="M111 188C181 57 403 62 525 197" strokeDasharray="4 10" />
    <g className="ml-hand-left"><path className="ml-art-terra" d="M0 204l113-39 33 109-112 67Z"/><path className="ml-art-sand ml-art-outline" d="m119 178 61-26c21-10 48-24 59-12 7 9-3 19-16 26l-30 19 93-17c14-3 26 0 26 10 0 9-8 13-19 16l-75 24 88-14c13-2 21 3 19 12-1 8-10 12-22 15l-95 26c-41 11-61 21-66 4Z"/><path className="ml-art-outline" d="m183 217 47-10m-78-17 18 54"/></g>
    <g className="ml-hand-right"><path className="ml-art-charcoal" d="m640 180-107-21-25 109 132 42Z"/><path className="ml-art-sand ml-art-outline" d="m531 174-63-25c-21-9-47-25-58-13-7 8 3 18 16 25l29 18-83-14c-15-3-27 0-27 10 0 9 9 14 20 17l66 22-82-13c-13-2-21 3-19 12 1 8 10 12 22 15l89 26c41 11 56 23 62 4Z"/><path className="ml-art-outline" d="m464 210-35-9m76-12-17 49"/></g>
    <g className="ml-medicine-pass"><rect x="272" y="139" width="98" height="66" rx="6" className="ml-art-cream ml-art-outline" transform="rotate(-12 320 172)"/>{[0,1,2,3,4,5].map((i)=><ellipse key={i} cx={286+(i%3)*25} cy={155+Math.floor(i/3)*27} rx="8" ry="11" className="ml-art-terra" transform="rotate(-12 320 172)"/>)}</g>
    <g className="ml-hand-bottom"><path className="ml-art-terra" d="m233 380 19-61 95-2 23 63Z"/><path className="ml-art-sand ml-art-outline" d="m252 324-22-38c-15-22-21-36-12-41 10-5 18 8 32 23l16 12-2-57c-1-15 4-25 12-24 10 1 11 11 13 24l7 40 7-53c2-15 8-22 16-19 8 3 8 12 7 25l-1 48 10-38c3-12 9-17 15-14 7 3 6 12 4 23l-8 66c-2 19-19 34-19 34Z"/></g>
    <path className="ml-art-outline ml-leaf-draw" d="M87 113 58 65m20 33c-39 1-31-21-31-21 20-3 28 10 31 21Zm-12-21c8-33 25-20 25-20-1 18-12 20-25 20Zm490 52 31-58m-18 33c34-8 27-24 27-24-20-1-26 12-27 24Zm9-22c-14-23-27-13-27-13 3 15 13 18 27 13Z"/>
    <path className="ml-art-terra ml-heart-beat" d="M329 72c-24-25-41 7 0 30 40-26 23-54 0-30Z"/><path className="ml-art-outline" d="m180 74 2-13m-8 7 15-2m270 230 3-13m-9 7 15-2" />
  </svg>
}

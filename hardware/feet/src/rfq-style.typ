// Shared page style for the RFQ documents of the DuckBuddy feet.
#let m = json("/measurements.json")
#let f1(v) = {
  // one decimal, always shown (2.0, not 2)
  let t = calc.round(v * 10)
  str(int(calc.quo(int(t), 10))) + "." + str(int(calc.rem(calc.abs(int(t)), 10)))
}

#let doc(title: "", body) = {
  set document(title: title, author: "Rafael Caricio", date: none)  // no date: same bytes on every build
  set page(paper: "a4", margin: (x: 20mm, top: 22mm, bottom: 20mm),
    header: [#set text(8pt, fill: luma(90)); DuckBuddy robot feet — request for quotation #h(1fr) Rev A, 2026-11-07],
    footer: context [#set text(8pt, fill: luma(90)); Rafael Caricio · rafael\@caricio.com #h(1fr) Page #counter(page).display() of #counter(page).final().first()])
  set text(font: ("Helvetica Neue", "Helvetica", "Arial"), size: 10pt)
  set par(justify: false, leading: 0.6em)
  set heading(numbering: "1.")
  show heading.where(level: 1): set text(12pt)
  show heading: set block(above: 1.2em, below: 0.6em)
  set table(stroke: 0.4pt + luma(120), inset: 5pt)
  show table.cell.where(y: 0): set text(weight: "bold")
  text(16pt, weight: "bold", title)
  v(2mm)
  table(columns: (auto, 1fr),
    [Parts], [DB-FOOT-SOLE-L, DB-FOOT-SOLE-R (soles, elastomer); optional DB-FOOT-L, DB-FOOT-R (rigid feet)],
    [Files], [`sole_left.step`, `sole_right.step`, `foot_left.step`, `foot_right.step` (in `duckbuddy-feet-cad.zip`; STL copies on request), drawing `duckbuddy-feet-drawing.pdf`],
    [Contact], [Rafael Caricio, rafael\@caricio.com],
  )
  body
}

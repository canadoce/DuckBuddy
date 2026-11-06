import { type ChipProps } from "tscircuit"
// S8550 PNP (JSCJ, LCSC C105432, a JLCPCB basic part), SOT-23. Pin order from the JSCJ data sheet:
// 1 base, 2 emitter, 3 collector (the same as MMBT3906). Ratings: VCEO -25 V, VEBO -5 V, IC -0.5 A, hFE 120-400.
// The pads are the MMBT3906 (C7420354) land pattern used before, so the layout did not change;
// JLCPCB's own S8550 footprint has the same pin positions and pin 1 side, with longer pads.
const pinLabels = {
  "pin1": [
    "B"
  ],
  "pin2": [
    "E"
  ],
  "pin3": [
    "C"
  ]
} as const
export const S8550 = (props: ChipProps<typeof pinLabels>) => (
  <chip
    footprint={<footprint>
        <smtpad portHints={["pin1"]} pcbX="0.9999979999998914mm" pcbY="-0.9499599999999191mm" layer="top" width="0.9999979999999999mm" height="0.6500114mm" shape="rect" />
<smtpad portHints={["pin2"]} pcbX="0.9999979999998914mm" pcbY="0.9499599999999191mm" layer="top" width="0.9999979999999999mm" height="0.6500114mm" shape="rect" />
<smtpad portHints={["pin3"]} pcbX="-0.9999979999998914mm" pcbY="0mm" layer="top" width="0.9999979999999999mm" height="0.6500114mm" shape="rect" />
<silkscreenpath route={[{"x":0.726211400000011,"y":1.5262098000000606},{"x":-0.726211400000011,"y":1.5262098000000606},{"x":-0.726211400000011,"y":0.49458879999997407}]} strokeWidth={0.15239999999999998} />
<silkscreenpath route={[{"x":0.726211400000011,"y":-1.5262097999999469},{"x":-0.726211400000011,"y":-1.5262097999999469},{"x":-0.726211400000011,"y":-0.49458879999997407}]} strokeWidth={0.15239999999999998} />
<silkscreenpath route={[{"x":0.726211400000011,"y":0.45539659999997184},{"x":0.726211400000011,"y":-0.45539659999985815}]} strokeWidth={0.15239999999999998} />
<courtyardoutline outline={[{"x":-1.748600000000124,"y":1.774000000000001},{"x":1.7993999999998778,"y":1.774000000000001},{"x":1.7993999999998778,"y":-1.774000000000001},{"x":-1.748600000000124,"y":-1.774000000000001},{"x":-1.748600000000124,"y":1.774000000000001}]} layer="top" />
      </footprint>}
    pinLabels={pinLabels}
    pinAttributes={{
  "pin1": {
    "isPassive": true
  },
  "pin2": {
    "isPassive": true
  },
  "pin3": {
    "isPassive": true
  }
}}
    supplierPartNumbers={{
  "jlcpcb": [
    "C105432"
  ]
}}
    manufacturerPartNumber="S8550"
    cadModel={{
        objUrl: "https://modelcdn.tscircuit.com/easyeda_models/assets/C105432.obj?uuid=cefd4596db214da394d9632b2b88f8f2",
        stepUrl: "https://modelcdn.tscircuit.com/easyeda_models/assets/C105432.step?uuid=cefd4596db214da394d9632b2b88f8f2",
        pcbRotationOffset: 90,
        modelOriginPosition: { x: 0.000012699999956566899, y: 0, z: 0 },
    }}
    {...props}
  />
)

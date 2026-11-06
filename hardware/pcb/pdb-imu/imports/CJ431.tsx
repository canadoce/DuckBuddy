import type { ChipProps } from "@tscircuit/props"

// Pin order from the CJ431 datasheet (JCET, SOT-23): 1 reference, 2 cathode, 3 anode.
// The EasyEDA library part for C3113 has 1 and 2 swapped (that is the CD431 order), so the
// labels and symbol below are corrected by hand; the pads are unchanged.
const pinLabels = {
  pin1: ["R"],
  pin2: ["K"],
  pin3: ["A"]
} as const

export const CJ431 = (props: ChipProps<typeof pinLabels>) => {
  return (
    <chip
      pinLabels={pinLabels}
      symbol={
        <symbol>
          <port name="pin2" pinNumber={2} aliases={["K"]} direction="up" schX={0.3} schY={0.8} schStemLength={0.4} />
          <port name="pin1" pinNumber={1} aliases={["R"]} direction="left" schX={-0.5} schY={0} schStemLength={0.4} />
          <port name="pin3" pinNumber={3} aliases={["A"]} direction="down" schX={0.3} schY={-0.8} schStemLength={0.4} />
          <schematicpath points={[{"x":0.3,"y":0.2},{"x":0.3,"y":-0.2}]} strokeColor="#880000" />
          <schematicpath points={[{"x":0.3,"y":0.12},{"x":0.2,"y":-0.06},{"x":0.4,"y":-0.06},{"x":0.3,"y":0.12}]} strokeColor="#880000" />
          <schematicpath points={[{"x":0.24,"y":0.12},{"x":0.36,"y":0.12},{"x":0.38,"y":0.14}]} strokeColor="#880000" />
          <schematicpath points={[{"x":0.24,"y":0.12},{"x":0.22,"y":0.1}]} strokeColor="#880000" />
          <schematicpath points={[{"x":0.06,"y":0},{"x":0.2,"y":0}]} strokeColor="#880000" />
          <schematicrect schX={0.2} schY={0} width={0.6} height={0.8} strokeWidth={0.02} color="#880000" />
        </symbol>
      }
      supplierPartNumbers={{
  "jlcpcb": [
    "C3113"
  ]
}}
      manufacturerPartNumber="CJ431"
      footprint={<footprint>
        <smtpad portHints={["pin1"]} pcbX="1.235075mm" pcbY="-0.94996mm" width="1.0700004mm" height="0.5999988mm" shape="rect" />
<smtpad portHints={["pin2"]} pcbX="1.235075mm" pcbY="0.94996mm" width="1.0700004mm" height="0.5999988mm" shape="rect" />
<smtpad portHints={["pin3"]} pcbX="-1.235075mm" pcbY="0mm" width="1.0700004mm" height="0.5999988mm" shape="rect" />
<silkscreenpath route={[{"x":0.8760714000002281,"y":1.5361919999999145},{"x":-0.8763253999998142,"y":1.5361919999999145},{"x":-0.8763253999998142,"y":0.49458879999997407}]} />
<silkscreenpath route={[{"x":0.8760714000002281,"y":-1.5361920000000282},{"x":-0.8763253999998142,"y":-1.5361920000000282},{"x":-0.8763253999998142,"y":-0.49458879999997407}]} />
<silkscreenpath route={[{"x":0.8760714000002281,"y":0.45539659999997184},{"x":0.8760714000002281,"y":-0.45539659999985815}]} />
<silkscreentext text="{NAME}" pcbX="-0.012827mm" pcbY="2.524mm" anchorAlignment="center" fontSize="1mm" />
<courtyardoutline outline={[{"x":-2.0281269999999267,"y":1.774000000000001},{"x":2.0024730000002364,"y":1.774000000000001},{"x":2.0024730000002364,"y":-1.7993999999999915},{"x":-2.0281269999999267,"y":-1.7993999999999915},{"x":-2.0281269999999267,"y":1.774000000000001}]} />
      </footprint>}
      cadModel={{
        objUrl: "https://modelcdn.tscircuit.com/easyeda_models/assets/C3113.obj?uuid=cefd4596db214da394d9632b2b88f8f2",
        stepUrl: "https://modelcdn.tscircuit.com/easyeda_models/assets/C3113.step?uuid=cefd4596db214da394d9632b2b88f8f2",
        pcbRotationOffset: 90,
        modelOriginPosition: { x: 0.000012699999956566899, y: 0, z: 0 },
      }}
      {...props}
    />
  )
}
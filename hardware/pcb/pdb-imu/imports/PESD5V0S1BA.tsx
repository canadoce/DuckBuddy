import type { ChipProps } from "@tscircuit/props"

const pinLabels = {
  pin1: ["pin1"],
  pin2: ["pin2"]
} as const

export const PESD5V0S1BA = (props: ChipProps<typeof pinLabels>) => {
  return (
    <chip
      pinLabels={pinLabels}
      symbol={
        <symbol>
          <port name="pin2" pinNumber={2} aliases={["2"]} direction="right" schX={0.4} schY={0} schStemLength={0.2} />
          <port name="pin1" pinNumber={1} aliases={["1"]} direction="left" schX={-0.4} schY={0} schStemLength={0.2} />
          <schematicpath points={[{"x":-0.2,"y":0.1},{"x":0,"y":0},{"x":-0.2,"y":-0.1},{"x":-0.2,"y":0.1}]} strokeColor="#880000" />
          <schematicpath points={[{"x":0.2,"y":0.1},{"x":0,"y":0},{"x":0.2,"y":-0.1},{"x":0.2,"y":0.1}]} strokeColor="#880000" />
          <schematicpath points={[{"x":-0.04,"y":0.12},{"x":-0.04,"y":0.12},{"x":0,"y":0.12},{"x":0,"y":-0.12},{"x":0.04,"y":-0.12},{"x":0.04,"y":-0.12}]} strokeColor="#880000" />
          <schematictext schX={0} schY={0.32} text="{NAME}" fontSize={0.2} anchor="bottom_center" />
        </symbol>
      }
      supplierPartNumbers={{
  "jlcpcb": [
    "C2827694"
  ]
}}
      manufacturerPartNumber="PESD5V0S1BA"
      footprint="smdpads2_p2.41mm_pw0.8mm_ph0.8mm_cyw3.71mm_cyh1.8mm"
      cadModel={{
        objUrl: "https://modelcdn.tscircuit.com/easyeda_models/assets/C2827694.obj?uuid=5284e5723bda45e1a33dc55b8531c926",
        stepUrl: "https://modelcdn.tscircuit.com/easyeda_models/assets/C2827694.step?uuid=5284e5723bda45e1a33dc55b8531c926",
        pcbRotationOffset: 0,
        modelOriginPosition: { x: 0.00003810000009707437, y: -0.00016510000000380387, z: 0 },
      }}
      {...props}
    />
  )
}
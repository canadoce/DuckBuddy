import type { ChipProps } from "@tscircuit/props"

const pinLabels = {
  pin1: ["pin1"],
  pin2: ["pin2"]
} as const

export const A_1210L300_24WR = (props: ChipProps<typeof pinLabels>) => {
  return (
    <chip
      pinLabels={pinLabels}
      symbol={
        <symbol>
          <schematicpath points={[{"x":-0.2,"y":0},{"x":0.2,"y":0}]} strokeColor="#8D2323" />
          <port name="pin2" pinNumber={2} aliases={["2"]} direction="right" schX={0.4} schY={0} schStemLength={0.2} />
          <port name="pin1" pinNumber={1} aliases={["1"]} direction="left" schX={-0.4} schY={0} schStemLength={0.2} />
          <schematicrect schX={0} schY={0} width={0.52} height={0.12} strokeWidth={0.02} color="#880000" />
        </symbol>
      }
      supplierPartNumbers={{
  "jlcpcb": [
    "C22379947"
  ]
}}
      manufacturerPartNumber="1210L300/24WR"
      footprint="smdpads2_p3.1999mm_pw1.485mm_ph2.781mm_cyw5.834mm_cyh3.802mm"
      cadModel={{
        objUrl: "https://modelcdn.tscircuit.com/easyeda_models/assets/C22379947.obj?uuid=7620d943bdff48279d2385e981310ade",
        stepUrl: "https://modelcdn.tscircuit.com/easyeda_models/assets/C22379947.step?uuid=7620d943bdff48279d2385e981310ade",
        pcbRotationOffset: 0,
        modelOriginPosition: { x: 0, y: 0, z: 0 },
      }}
      {...props}
    />
  )
}
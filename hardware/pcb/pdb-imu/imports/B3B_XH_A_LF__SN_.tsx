import type { ChipProps } from "@tscircuit/props"

const pinLabels = {
  pin1: ["pin1"],
  pin2: ["pin2"],
  pin3: ["pin3"]
} as const

export const B3B_XH_A_LF__SN_ = (props: ChipProps<typeof pinLabels>) => {
  return (
    <chip
      pinLabels={pinLabels}
      supplierPartNumbers={{
  "jlcpcb": [
    "C144394"
  ]
}}
      manufacturerPartNumber="B3B-XH-A(LF)(SN)"
      footprint="pinrow3_nosquareplating_p2.5mm_od1.55mm_id0.9mm"
      cadModel={{
        objUrl: "https://modelcdn.tscircuit.com/easyeda_models/assets/C144394.obj?uuid=7b9459f45f5f46e380bc2dba5f93c262",
        stepUrl: "https://modelcdn.tscircuit.com/easyeda_models/assets/C144394.step?uuid=7b9459f45f5f46e380bc2dba5f93c262",
        pcbRotationOffset: 0,
        modelOriginPosition: { x: 0.06375400000013087, y: -0.013601699999981065, z: -0.0000064000000006281255 },
      }}
      {...props}
    />
  )
}
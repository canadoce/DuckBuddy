import type { ResistorProps } from "@tscircuit/props"

export const RLM12FTCMR002 = (props: Omit<ResistorProps, "resistance">) => {
  const { name = "R1", ...restProps } = props

  return (
    <resistor
      name={name}
      resistance="2mohm"
      supplierPartNumbers={{
  "jlcpcb": [
    "C710257"
  ]
}}
      manufacturerPartNumber="RLM12FTCMR002"
      footprint="smdpads2_p2.9576mm_pw1.2075mm_ph1.701mm"
      cadModel={{
        objUrl: "https://modelcdn.tscircuit.com/easyeda_models/assets/C710257.obj?uuid=da5f078ee43c429f91838a456f48f0a8",
        stepUrl: "https://modelcdn.tscircuit.com/easyeda_models/assets/C710257.step?uuid=da5f078ee43c429f91838a456f48f0a8",
        pcbRotationOffset: 0,
        modelOriginPosition: { x: 0, y: 0, z: 0 },
      }}
      {...restProps}
    />
  )
}
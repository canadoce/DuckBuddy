import type { ChipProps } from "@tscircuit/props"

const pinLabels = {
  pin1: ["S1"],
  pin2: ["S2"],
  pin3: ["S3"],
  pin4: ["G"],
  pin5: ["D4"],
  pin6: ["D3"],
  pin7: ["D2"],
  pin8: ["D1"],
  pin9: ["D5"]
} as const

const footprinterPinLabels = {
  ...pinLabels,
  "pin9": [...pinLabels["pin9"], "thermalpad"],
} as const

export const AON7410 = (props: ChipProps<typeof pinLabels>) => {
  return (
    <chip
      pinLabels={footprinterPinLabels}
      supplierPartNumbers={{
  "jlcpcb": [
    "C269266"
  ]
}}
      manufacturerPartNumber="AON7410"
      footprint="dfn8_thermalpad2.1mmx2.4mm_thermalpadcenteroffsetx0.35mm_p0.65mm_w3.8mm_pw0.4mm_pl0.8mm_pin1location(leftside,bottom)"
      cadModel={{
        objUrl: "https://modelcdn.tscircuit.com/easyeda_models/assets/C269266.obj?uuid=57a4d17d2f324694a8410e1537ff505d",
        stepUrl: "https://modelcdn.tscircuit.com/easyeda_models/assets/C269266.step?uuid=57a4d17d2f324694a8410e1537ff505d",
        pcbRotationOffset: 90,
        modelOriginPosition: { x: 0, y: 0, z: 0 },
      }}
      {...props}
    />
  )
}
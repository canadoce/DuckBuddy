import type { ChipProps } from "@tscircuit/props"

const pinLabels = {
  pin1: ["OE"],
  pin2: ["A"],
  pin3: ["GND"],
  pin4: ["Y"],
  pin5: ["VCC"]
} as const

const pinAttributes = {
  pin3: {requiresGround: true},
  pin5: {requiresPower: true}
} as const

export const A_74LVC1G126GW = (props: ChipProps<typeof pinLabels>) => {
  return (
    <chip
      pinLabels={pinLabels}
      pinAttributes={pinAttributes}
      supplierPartNumbers={{
  "jlcpcb": [
    "C52140429"
  ]
}}
      manufacturerPartNumber="74LVC1G126GW"
      footprint="dfn6_missing(5)_p0.65mm_w2.4mm_pw0.36mm_pl0.6mm_pin1location(leftside,bottom)"
      cadModel={{
        objUrl: "https://modelcdn.tscircuit.com/easyeda_models/assets/C52140429.obj?uuid=88527de39a584ba3a27df723f14634b5",
        stepUrl: "https://modelcdn.tscircuit.com/easyeda_models/assets/C52140429.step?uuid=88527de39a584ba3a27df723f14634b5",
        pcbRotationOffset: 0,
        modelOriginPosition: { x: 0, y: -0.000012699999984988608, z: -0.15 },
      }}
      {...props}
    />
  )
}
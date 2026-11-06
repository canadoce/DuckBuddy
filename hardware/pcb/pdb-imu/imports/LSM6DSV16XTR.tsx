import type { ChipProps } from "@tscircuit/props"

const pinLabels = {
  pin1: ["SDO", "SA0"],
  pin2: ["SDx"],
  pin3: ["SCx"],
  pin4: ["INT1"],
  pin5: ["Vdd_IO"],
  pin6: ["GND1"],
  pin7: ["GND2"],
  pin8: ["Vdd"],
  pin9: ["INT2"],
  pin10: ["OCS_Aux"],
  pin11: ["SDO_Aux"],
  pin12: ["CS"],
  pin13: ["SCL"],
  pin14: ["SDA"]
} as const

const pinAttributes = {
  pin6: {requiresGround: true},
  pin7: {requiresGround: true},
  pin8: {requiresPower: true}
} as const

export const LSM6DSV16XTR = (props: ChipProps<typeof pinLabels>) => {
  return (
    <chip
      pinLabels={pinLabels}
      pinAttributes={pinAttributes}
      supplierPartNumbers={{
  "jlcpcb": [
    "C5267406"
  ]
}}
      manufacturerPartNumber="LSM6DSV16XTR"
      footprint="lga_w2.94mm_h2.44mm_pw0.27mm_pl0.6mm_pin1location(rightside,bottom)"
      cadModel={{
        objUrl: "https://modelcdn.tscircuit.com/easyeda_models/assets/C5267406.obj?uuid=1e27b85210a0453eb361fa5def23f788",
        stepUrl: "https://modelcdn.tscircuit.com/easyeda_models/assets/C5267406.step?uuid=1e27b85210a0453eb361fa5def23f788",
        pcbRotationOffset: 180,
        modelOriginPosition: { x: -0.000025399999913133797, y: 0.0000889000000370288, z: -0.21 },
      }}
      {...props}
    />
  )
}
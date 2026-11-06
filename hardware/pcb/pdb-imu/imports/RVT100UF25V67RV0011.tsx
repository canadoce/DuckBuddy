import type { CapacitorProps } from "@tscircuit/props"

export const RVT100UF25V67RV0011 = (props: Omit<CapacitorProps, "capacitance">) => {
  const { name = "C1", ...restProps } = props

  return (
    <capacitor
      name={name}
      capacitance="100uF"
      polarized
      supplierPartNumbers={{
  "jlcpcb": [
    "C2836443"
  ]
}}
      manufacturerPartNumber="RVT100UF25V67RV0011"
      footprint="cap_p5.3398mm_pw3.5mm_ph1.2mm"
      cadModel={{
        objUrl: "https://modelcdn.tscircuit.com/easyeda_models/assets/C2836443.obj?uuid=4098ac4942764b88998acce28312dfd8",
        stepUrl: "https://modelcdn.tscircuit.com/easyeda_models/assets/C2836443.step?uuid=4098ac4942764b88998acce28312dfd8",
        pcbRotationOffset: 180,
        modelOriginPosition: { x: 0.00005080000016732811, y: 0.00012700000002041634, z: -0.02 },
      }}
      {...restProps}
    />
  )
}
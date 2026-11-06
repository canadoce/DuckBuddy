import { type ChipProps } from "tscircuit"

// STM32G031F8P6, TSSOP-20 (LCSC C529334). Pin names from the STM32G031x4/x6/x8
// datasheet (DS12992), TSSOP20 pinout. Pins that bond several GPIOs carry all names.
const pinLabels = {
  pin1: ["PB7", "PB8"],
  pin2: ["PB9", "PC14"],
  pin3: ["PC15"],
  pin4: ["VDD"],
  pin5: ["VSS"],
  pin6: ["NRST"],
  pin7: ["PA0"],
  pin8: ["PA1"],
  pin9: ["PA2"],
  pin10: ["PA3"],
  pin11: ["PA4"],
  pin12: ["PA5"],
  pin13: ["PA6"],
  pin14: ["PA7"],
  pin15: ["PB0", "PB1", "PB2", "PA8"],
  pin16: ["PA11", "PA9"],
  pin17: ["PA12", "PA10"],
  pin18: ["PA13", "SWDIO"],
  pin19: ["PA14", "SWCLK", "BOOT0"],
  pin20: ["PB3", "PB4", "PB5", "PB6"],
} as const

export const STM32G031F8P6 = (props: ChipProps<typeof pinLabels>) => (
  <chip
    footprint="tssop20_p0.65mm_w3.9999mm_pw0.364mm_pl1.742mm_rounded0.182mm_pin1location(leftside,bottom)"
    pinLabels={pinLabels}
    pinAttributes={{
      VDD: { requiresPower: true },
      VSS: { requiresGround: true },
    }}
    supplierPartNumbers={{ jlcpcb: ["C529334"] }}
    manufacturerPartNumber="STM32G031F8P6"
    cadModel={{
      objUrl: "https://modelcdn.tscircuit.com/easyeda_models/assets/C529334.obj?uuid=f8ba5b4174b9490d8c445fbe2ed40b80",
      stepUrl: "https://modelcdn.tscircuit.com/easyeda_models/assets/C529334.step?uuid=f8ba5b4174b9490d8c445fbe2ed40b80",
      pcbRotationOffset: 90,
      modelOriginPosition: { x: 0, y: 0.000012700000070253736, z: -0.019205 },
    }}
    {...props}
  />
)

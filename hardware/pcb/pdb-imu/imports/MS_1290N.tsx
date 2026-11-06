import type { SwitchProps } from "@tscircuit/props"

const pinLabels = {
  pin1: ["pin1"],
  pin2: ["pin2"],
  pin3: ["pin3"]
} as const

export const MS_1290N = (props: SwitchProps) => {
  const { name = "SW1", ...restProps } = props

  return (
    <switch
      name={name}
      pinLabels={pinLabels}
      supplierPartNumbers={{
  "jlcpcb": [
    "C19188866"
  ]
}}
      manufacturerPartNumber="MS-1290N"
      footprint={<footprint>
        <hole pcbX="-1.499997mm" pcbY="-1.2375134mm" diameter="0.7999984mm" />
<hole pcbX="1.499997mm" pcbY="-1.2375134mm" diameter="0.7999984mm" />
<smtpad portHints={["pin3"]} pcbX="2.250059mm" pcbY="0.6375146mm" width="0.7999984mm" height="1.999996mm" shape="rect" />
<smtpad portHints={["pin2"]} pcbX="0.749935mm" pcbY="0.6375146mm" width="0.7999984mm" height="1.999996mm" shape="rect" />
<smtpad portHints={["pin1"]} pcbX="-2.250059mm" pcbY="0.6375146mm" width="0.7999984mm" height="1.999996mm" shape="rect" />
<silkscreenpath route={[{"x":1.5538704000000507,"y":-4.188485399999877},{"x":1.5538704000000507,"y":-2.688488399999983}]} />
<silkscreenpath route={[{"x":0.2539238000000523,"y":-4.188485399999877},{"x":0.2539238000000523,"y":-2.688488399999983}]} />
<silkscreenpath route={[{"x":0.2539238000000523,"y":-4.188485399999877},{"x":1.5538704000000507,"y":-4.188485399999877}]} />
<silkscreenpath route={[{"x":3.3999169999999594,"y":-2.6374852000000146},{"x":3.3999169999999594,"y":0.25651459999994586}]} />
<silkscreenpath route={[{"x":2.881071200000065,"y":0.25651459999994586},{"x":3.301923800000054,"y":0.25651459999994586}]} />
<silkscreenpath route={[{"x":1.381074200000171,"y":0.25651459999994586},{"x":1.6187928000001648,"y":0.25651459999994586}]} />
<silkscreenpath route={[{"x":-1.6189197999999578,"y":0.25651459999994586},{"x":0.11879580000004353,"y":0.25651459999994586}]} />
<silkscreenpath route={[{"x":-3.400069399999893,"y":-2.6374852000000146},{"x":-3.400069399999893,"y":0.25651459999994586},{"x":-2.881198199999858,"y":0.25651459999994586}]} />
<silkscreenpath route={[{"x":3.3999169999999594,"y":-2.6374852000000146},{"x":-3.400069399999893,"y":-2.6374852000000146}]} />
<silkscreentext text="{NAME}" pcbX="-0.024765mm" pcbY="2.6281146mm" anchorAlignment="center" fontSize="1mm" />
<fabricationnotepath route={[{"x":0,"y":-2.6644853999999896},{"x":0,"y":-4.1884853999999905},{"x":1.2699999999999818,"y":-4.1884853999999905},{"x":1.2699999999999818,"y":-2.6644853999999896},{"x":0,"y":-2.6644853999999896}]} strokeWidth="0.254mm" />
<courtyardoutline outline={[{"x":-3.6910649999999805,"y":1.8781146000001172},{"x":3.64153500000009,"y":1.8781146000001172},{"x":3.64153500000009,"y":-4.438485399999877},{"x":-3.6910649999999805,"y":-4.438485399999877},{"x":-3.6910649999999805,"y":1.8781146000001172}]} />
      </footprint>}
      cadModel={{
        objUrl: "https://modelcdn.tscircuit.com/easyeda_models/assets/C19188866.obj?uuid=6ee59496afe643dca9ce836ac2e263e3",
        stepUrl: "https://modelcdn.tscircuit.com/easyeda_models/assets/C19188866.step?uuid=6ee59496afe643dca9ce836ac2e263e3",
        pcbRotationOffset: 0,
        modelOriginPosition: { x: 0.00007619999996677507, y: 1.233474299999898, z: -1.400001 },
      }}
      {...restProps}
    />
  )
}
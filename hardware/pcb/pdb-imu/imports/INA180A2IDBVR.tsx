import { type ChipProps } from "tscircuit"
const pinLabels = {
  "pin1": [
    "OUT"
  ],
  "pin2": [
    "GND"
  ],
  "pin3": [
    "IN_POS"
  ],
  "pin4": [
    "IN_NEG"
  ],
  "pin5": [
    "VS"
  ]
} as const
export const INA180A2IDBVR = (props: ChipProps<typeof pinLabels>) => (
  <chip
    footprint={<footprint>
        <smtpad portHints={["pin1"]} pcbX="-0.9499599999999191mm" pcbY="-1.1581701499999326mm" layer="top" width="0.48999139999999997mm" height="1.1569954mm" shape="rect" />
<smtpad portHints={["pin2"]} pcbX="0mm" pcbY="-1.1581701499999326mm" layer="top" width="0.48999139999999997mm" height="1.1569954mm" shape="rect" />
<smtpad portHints={["pin3"]} pcbX="0.9499599999998054mm" pcbY="-1.1581701499999326mm" layer="top" width="0.48999139999999997mm" height="1.1569954mm" shape="rect" />
<smtpad portHints={["pin4"]} pcbX="0.9499599999998054mm" pcbY="1.1491658500000312mm" layer="top" width="0.48999139999999997mm" height="1.1750040000000002mm" shape="rect" />
<smtpad portHints={["pin5"]} pcbX="-0.9499599999999191mm" pcbY="1.1491658500000312mm" layer="top" width="0.48999139999999997mm" height="1.1750040000000002mm" shape="rect" />
<silkscreenpath route={[{"x":-1.5262098000000606,"y":-0.8557069500000125},{"x":-1.5262098000000606,"y":0.8467026499999974}]} strokeWidth={0.15239999999999998} />
<silkscreenpath route={[{"x":1.5262097999998332,"y":-0.8557069500000125},{"x":1.5262097999998332,"y":0.8467026499999974}]} strokeWidth={0.15239999999999998} />
<silkscreenpath route={[{"x":0.4764023999998699,"y":0.8467026499999974},{"x":-0.4764023999999836,"y":0.8467026499999974}]} strokeWidth={0.15239999999999998} />
<silkscreencircle pcbX={-1.6510000000000673} pcbY={-1.1475021500000366} radius={0.150114} layer="top" strokeWidth={0.29999939999999997} />
<courtyardoutline outline={[{"x":-2.0534000000000106,"y":1.998097850000022},{"x":1.7739999999998872,"y":1.998097850000022},{"x":1.7739999999998872,"y":-2.108702149999999},{"x":-2.0534000000000106,"y":-2.108702149999999},{"x":-2.0534000000000106,"y":1.998097850000022}]} layer="top" />
      </footprint>}
    pinLabels={pinLabels}
    pinAttributes={{
  "pin1": {
    "isOutput": true
  },
  "pin2": {
    "mustBeConnected": true,
    "requiresGround": true
  },
  "pin3": {
    "isInput": true
  },
  "pin4": {
    "isInput": true
  },
  "pin5": {
    "isInput": true,
    "mustBeConnected": true,
    "requiresPower": true,
    "shouldHaveDecouplingCapacitor": true,
    "recommendedDecouplingCapacitorCapacitance": "100nF"
  }
}}
    supplierPartNumbers={{
  "jlcpcb": [
    "C192764"
  ]
}}
    manufacturerPartNumber="INA180A2IDBVR"
    cadModel={{
        objUrl: "https://modelcdn.tscircuit.com/easyeda_models/assets/C192764.obj?uuid=460193f9bf2d42e58cf3c2f675b07dc6",
        stepUrl: "https://modelcdn.tscircuit.com/easyeda_models/assets/C192764.step?uuid=460193f9bf2d42e58cf3c2f675b07dc6",
        pcbRotationOffset: 90,
        modelOriginPosition: {"x":0.004489450000050965,"y":0.000012700000070253736,"z":-0.049083},
    }}
    {...props}
  />
)
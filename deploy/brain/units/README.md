# The brain's user services

`deploy/brain/deploy.sh` copies these to `~/.config/systemd/user` and enables robotd-dev, tofd-dev,
lifed-dev, voiced-dev, visiond-dev, duckweb-dev, duckjev-dev and duckbrain-dev. They are user units: `systemctl --user`, no sudo.
They start at boot because install.sh turns lingering on (`sudo loginctl enable-linger $USER`).

| Unit | Runs | Notes |
|---|---|---|
| robotd-dev | `~/robot/robotd --params ~/robot/active.toml $ROBOTD_ARGS` | arguments from `~/robot/robotd.env`; not restarted on a crash (a restart drops a standing robot) |
| tofd-dev | `~/robot/tofd --bus /dev/i2c-2` | the ToF on the HAT's Qwiic J8 |
| lifed-dev | `~/lifed/lifed.py $LIFED_ARGS` | arguments from `~/robot/lifed.env`; follows robotd up and down |
| voiced-dev | `~/voiced/hearing.py` (its venv) | follows lifed |
| visiond-dev | `~/visiond/visiond.py` | the camera through `~/visiond/duckcam`; stop it before a camera test |
| duckweb-dev | `~/duckweb/duckweb.py` | the phone page on :8088 |
| duckjev-dev | `~/duckbrain/judge.py 8211` | Jev on 127.0.0.1:8211, settings from `~/.config/duckbrain/jev.env` (../README.md) |
| duckbrain-dev | `~/duckbrain/server.py` | the online brain on 127.0.0.1:8210, settings from `~/.config/duckbrain/duckbrain.env` |
| padd-dev | `~/robot/padd` | the gamepad; not enabled: it walks the robot |
| frpc-dev | `~/frp/frpc` | the tunnel to a duckbrain on another machine; not enabled (duckbrain runs on the brain) |

- Change config: `ln -sfn other.toml ~/robot/active.toml && systemctl --user restart robotd-dev`.
- Scripted trials (`trial.sh`) want robotd but **not** padd: padd sends a zero twist every tick with the
  sticks centred, which overrides the trial's `robot.move` — `systemctl --user stop padd-dev` first.
- `start.sh` refuses while the service's robotd runs: `systemctl --user stop robotd-dev` to go manual.
- Logs: `~/robot/recs/<name>-service.log`.
- **Start on the pad powers a limp robot up and stands it** — hold the robot first.

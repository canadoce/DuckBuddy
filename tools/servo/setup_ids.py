# -*- coding: utf-8 -*-
"""Feetech HLS servo chain setup wizard: no need to unplug and replug each servo.

From the factory all 15 servos have ID=1. Several servos with the same ID on one bus answer together and overwrite each other, so you cannot address one of them.
But as long as **only the newly connected servo has ID 1 at any moment**, you can keep adding servos to the chain:

    Servo 1 connected alone -> ID 1 is unique -> change it to 15
    Servo 2 added to the chain -> chain is {15, 1}, ID 1 is still unique -> change it to 14
    ...
    Servo 15 added to the chain -> ID 1 is unique and the target is 1 -> no change needed

So IDs are given from high to low, and the last servo keeps ID 1 by itself. Along the harness the order is 15->14->...->1.

**Every run goes through all --count servos from the start** (it does not resume from where it stopped):
    - a servo that already has its target ID -> set up again in place (limits/mode/current/centering all redone), no need to unplug it;
    - target ID missing -> wait for you to add a new servo at the end of the chain, then change its ID.
So if a run was interrupted, or the centering of one servo was skipped, just run it again. Servos already done will not clash.

Current safety: 1.25mm connectors (JST GH/SH) are rated about 1A per contact. The servo's default goal current is 450 LSB
= 2.93A. This tool lowers it to 100 LSB = 0.65A by default, and at any moment only the servo being set up has torque on.
All the others keep torque off, so the total current is always that of one servo.

Usage:
    python setup_ids.py --port COM11 --count 15
    python setup_ids.py --port COM11 --verify          # check after all servos are connected
    python setup_ids.py --port COM11 --center 14,15    # only redo the centering
    python setup_ids.py --port COM11 --isolated        # old mode: connect each servo alone
"""
import argparse
import io
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8',
                              errors='replace', line_buffering=True)
import fts_bus as F

FRESH_ID = 1        # factory ID; the newly connected servo always has it


def clean_ping(bus, sid, tries=6):
    """Counts only if `tries` pings in a row all get a valid reply.

    When several servos share one ID, a correctly formed packet can still come out now and then, so a single ping is not reliable.
    Getting all of many pings in a row is very unlikely, so we use it to tell "exactly one servo" from "a clash".
    """
    for _ in range(tries):
        if bus.ping(sid) is None:
            return False
    return True


def raw_activity(bus, sid=FRESH_ID):
    """Did any bytes come back on the line at all (fragments from a clash also count)."""
    for _ in range(3):
        bus.s.reset_input_buffer()
        body = [sid, 0x02, 0x01]
        bus.s.write(bytes([0xFF, 0xFF] + body + [(~sum(body)) & 0xFF]))
        bus.s.flush()
        time.sleep(0.02)
        if bus.s.read(32):
            return True
    return False


def wait_for_new(bus, assigned, target, prompt):
    """Wait for the "next" servo to come online. Both cases count as arrived; returns which one:

    'target' -- a servo answers on the target ID (the one connected **already had its ID changed**, e.g. a rerun,
                or it was connected later than the loop reached it); set it up again in place, keep the ID;
    'fresh'  -- a new servo answers alone on ID 1; go through the ID change.
    """
    while True:
        input(prompt)
        gone = [i for i in assigned if not clean_ping(bus, i, tries=3)]
        if gone:
            print('  !! ID %s set up earlier does not answer now -- a connection is loose somewhere, check the wiring first.' % gone)
            continue
        if clean_ping(bus, target, tries=4):
            print('  A servo answers on ID %d -- it already has its new ID, setting it up again in place.' % target)
            return 'target'
        if clean_ping(bus, FRESH_ID):
            return 'fresh'
        if raw_activity(bus):
            print('  !! Several servos answer at once on ID %d (the replies are fragments).' % FRESH_ID)
            print('     Connect only one new servo at a time -- unplug the extra one.')
        else:
            where = ('No reply on ID %d.' % target if target == FRESH_ID else
                     'No reply on ID %d or on ID 1.' % target)
            print('  !! %s' % where)
            print('     Check: power, direction of the 3-wire cable, plugged in fully; when done **press Enter again** to retry.')
            print('     (A servo that already has its new ID is fine too; I will see it as soon as it is online)')


def configure(bus, cur_id, new_id, args):
    if cur_id != new_id:
        print('  Change ID: %d -> %d' % (cur_id, new_id))
        bus.w8(cur_id, F.LOCK, 0)          # unlock, so EEPROM writes are kept after power off
        time.sleep(0.05)
        bus.w8(cur_id, F.ID_ADDR, new_id)
        time.sleep(0.08)
        if not clean_ping(bus, new_id, tries=4):
            print('  !! No ping from ID %d after the change' % new_id)
            return False
        if clean_ping(bus, FRESH_ID, tries=4):
            print('  !! A servo still answers on ID %d -- more than one was connected, '
                  'this change may have gone to another servo.' % FRESH_ID)
            return False
        bus.w8(new_id, F.LOCK, 1)
        time.sleep(0.05)
        print('     OK')
    else:
        print('  Target is ID %d already, no change needed' % new_id)

    bus.w8(new_id, F.LOCK, 0)
    time.sleep(0.05)
    bus.w16(new_id, F.MIN_ANGLE, 0)
    time.sleep(0.03)
    bus.w16(new_id, F.MAX_ANGLE, 0 if args.multiturn else 4095)
    time.sleep(0.03)
    bus.w8(new_id, F.MODE, 0)              # position servo mode
    time.sleep(0.03)
    bus.w8(new_id, F.LOCK, 1)
    time.sleep(0.05)

    # The three below are in SRAM and are lost at power off; the robot firmware must write them again at every power on
    bus.w16(new_id, F.GOAL_CURR, args.current)
    time.sleep(0.03)
    bus.w16(new_id, F.GOAL_SPEED, args.speed)
    time.sleep(0.03)
    bus.w8(new_id, F.ACCEL, args.accel)
    time.sleep(0.03)

    gc = bus.r16(new_id, F.GOAL_CURR)
    stat = bus.r8(new_id, F.STATUS)
    print('  limits=%d/%d  mode=%d  goal current=%d(%.2fA)  speed=%d  voltage=%.1fV  status=%d'
          % (bus.r16(new_id, F.MIN_ANGLE), bus.r16(new_id, F.MAX_ANGLE),
             bus.r8(new_id, F.MODE), gc, gc * 0.0065,
             F.smag(bus.r16(new_id, F.GOAL_SPEED)),
             bus.r8(new_id, F.PRES_VOLT) / 10.0, stat))
    if stat:
        print('  !! Status bits are not 0 (BIT0 voltage, BIT1 magnetic encoder, BIT2 temperature, BIT3 current)')
    return True


def ask_yes_no(prompt):
    """Needs a clear y or n. Just pressing Enter does not count -- a silent skip would make people think the action ran."""
    while True:
        a = input(prompt).strip().lower()
        if a in ('y', 'yes'):
            return True
        if a in ('n', 'no'):
            return False
        print('    Please type y or n (just Enter does not count)')


def goto_center(bus, sid, args):
    """Move to the center and hold torque until the servo horn is fitted, then release. Only this servo gets power.

    The target is "the 2048+4096k nearest to the current position", not plain 2048: when the position feedback counts several turns,
    plain 2048 could make the servo spin several turns. It is watched the whole time: if the error grows 1000 counts past its best value, or the current
    is above 300 LSB 3 times in a row, torque is cut at once -- a runaway servo is stopped within 0.1 s, instead of turning for the full
    10 seconds while waiting for someone to press Enter (that is what happened with ID 4: 2.44A for about ten seconds).
    """
    # Safety: if this servo just lost power (power-off check, or a self reset from high current), 44/46 are back at the power-on defaults
    # 450/250. Without writing them again the centering would run with a 2.92A limit -- this happened to ID 13.
    bus.w16(sid, F.GOAL_CURR, args.current)
    time.sleep(0.03)
    bus.w16(sid, F.GOAL_SPEED, args.speed)
    time.sleep(0.03)
    p = bus.pos(sid)
    target = F.CENTER + 4096 * round((p - F.CENTER) / 4096.0)
    print('  current position = %d, target = %d (nearest center on the same turn), moving %d counts (%.1f°)'
          % (p, target, target - p, abs(target - p) * 0.087))
    if not ask_yes_no('  Move to center and hold torque? If the horn/linkage is fitted, the joint will move with it. '
                      'Type y or n: '):
        print('  Skipped, this servo gets no power')
        return
    bus.w16(sid, F.GOAL_POS, F.enc(p))     # set the target to the current position first, so it does not jump when torque comes on
    time.sleep(0.03)
    bus.w8(sid, F.TORQUE, 1)
    time.sleep(0.05)
    bus.w16(sid, F.GOAL_POS, F.enc(target))

    ok = False; best = None; bad_cur = 0; i = 0; t0 = time.time()
    while time.time() - t0 < 10:
        time.sleep(0.1)
        i += 1
        p = bus.pos(sid)
        cur = F.smag(bus.r16(sid, F.PRES_CURR))
        err = abs(p - target)
        if best is None or err < best:
            best = err
        if err <= 3:
            ok = True
            break
        if err > best + 1000:
            print('    !! %d counts away from the target -- cutting torque to stop a runaway' % err)
            break
        if abs(cur) > 300:
            bad_cur += 1
            if bad_cur >= 3:
                print('    !! Current stays at %.2f A -- cutting torque' % (abs(cur) * 0.0065))
                break
        else:
            bad_cur = 0
        if i % 3 == 0:
            print('    pos=%6d  current=%5d (%.2f A)' % (p, cur, abs(cur) * 0.0065))

    if ok:
        print('    In position pos=%d, holding torque' % p)
        input('  Fit the servo horn at the neutral position, then press Enter to release torque... ')
    else:
        print('  !! Did not reach the position (last pos=%d) -- do not fit the horn on this one yet, check it by hand' % p)
    bus.w8(sid, F.TORQUE, 0)
    print('  Torque released.')


def verify(bus, count):
    ids = [i for i in range(0, 41) if clean_ping(bus, i, tries=3)]
    print('IDs answering on the bus (%d): %s' % (len(ids), sorted(ids)))
    missing = [i for i in range(1, count + 1) if i not in ids]
    extra = [i for i in ids if i < 1 or i > count]
    if missing:
        print('Missing: %s' % missing)
    if extra:
        print('Unexpected IDs: %s' % extra)
    if not ids:
        print('(No reply. If the raw replies are fragments, there is still an ID clash)')
        return
    print()
    print(' ID | pos   | volt  | temp | goal cur | spd  | limits    | mode | status')
    print('----+-------+-------+------+----------+------+-----------+------+-----')
    for sid in sorted(ids):
        print(' %2d | %5d | %4.1fV | %3d  |  %5d   | %4d | %4d/%-4d | %d    | %d'
              % (sid, bus.pos(sid), bus.r8(sid, F.PRES_VOLT) / 10.0,
                 bus.r8(sid, F.PRES_TEMP), bus.r16(sid, F.GOAL_CURR),
                 F.smag(bus.r16(sid, F.GOAL_SPEED)),
                 bus.r16(sid, F.MIN_ANGLE), bus.r16(sid, F.MAX_ANGLE),
                 bus.r8(sid, F.MODE), bus.r8(sid, F.STATUS)))
    if not missing and not extra:
        print()
        print('All %d servos are in place, no ID clashes.' % count)


def run_center(bus, args):
    """Only do the "move to center, fit the servo horn" step, for servos whose IDs are already set."""
    if args.center.strip().lower() == 'all':
        ids = [i for i in range(0, 41) if clean_ping(bus, i, tries=3)]
    else:
        ids = [int(x) for x in args.center.replace('\uff0c', ',').split(',') if x.strip()]
    print('IDs to center: %s' % ids)
    print('Goal current %d LSB = %.2f A, torque on only one servo at a time.'
          % (args.current, args.current * 0.0065))
    for sid in ids:
        print()
        print('--- ID %d ---' % sid)
        if not clean_ping(bus, sid, tries=4):
            print('  !! No ping from ID %d, skipping' % sid)
            continue
        # These three are in SRAM and are lost at power off; write them first, then move
        bus.w16(sid, F.GOAL_CURR, args.current)
        time.sleep(0.03)
        bus.w16(sid, F.GOAL_SPEED, args.speed)
        time.sleep(0.03)
        bus.w8(sid, F.ACCEL, args.accel)
        time.sleep(0.03)
        goto_center(bus, sid, args)
    return 0


def run_chain(bus, args):
    print('=' * 66)
    print('Feetech HLS servo chain setup   port=%s   %d servos' % (args.port, args.count))
    print('Every run goes through all servos from the start: IDs from %d down to 1.' % args.count)
    print('Servos that already have their target ID are set up again in place (with centering), no need to unplug;')
    print('for a missing one, add a new servo at the end of the chain. Torque is on for only one servo at a time.')
    print('Goal current %d LSB = %.2f A.' % (args.current, args.current * 0.0065))
    print('Best to cut servo power before adding the next one: hot-plugging 1.25mm connectors causes surges and arcing.')
    print('=' * 66)

    # Scan at start: every ID in 2..40 that answers counts as "already on the chain". ID 1 may be a newly connected servo,
    # so it does not count as "set up".
    present = [i for i in range(2, 41)
               if clean_ping(bus, i, tries=3)]
    stray = [i for i in present if i > args.count]
    if stray:
        print()
        print('!! The chain has IDs above --count=%d: %s' % (args.count, stray))
        print('   --count is wrong, or a servo from another robot got mixed in. Sort this out before going on.')
        return 1
    configured = [i for i in present if i <= args.count]
    fresh_now = clean_ping(bus, FRESH_ID, tries=3)
    if configured or fresh_now:
        print()
        print('Found at start: already set up %s%s'
              % (sorted(configured, reverse=True) or 'none',
                 ', plus one new servo with factory ID 1' if fresh_now else ''))
        if configured:
            print('They will be redone in place -- limits/mode/current/centering all done again.')

    # The **first new ID assignment** of every run gets a power-off check: the ID is stored in EEPROM, but
    # writes are not kept when the "lock flag" is not unlocked. Doing all of them without checking once could waste all 15.
    assigned_here = 0
    assigned = list(configured)

    for n, target in enumerate(range(args.count, 0, -1)):
        print()
        print('--- servo %d/%d  ->  ID %d ---' % (n + 1, args.count, target))
        if clean_ping(bus, target, tries=4):
            print('  A servo on the chain already has ID %d, setting it up again in place, ID unchanged.' % target)
            ok = configure(bus, target, target, args)
        else:
            if not assigned:
                tip = '  Connect only this servo, then press Enter (Ctrl+C to quit)... '
            else:
                tip = ('  Add the next servo at the end of the chain (keep the %d set up ones connected), '
                       'then press Enter... ' % len(assigned))
            mode = wait_for_new(bus, assigned, target, tip)
            if mode == 'target':
                ok = configure(bus, target, target, args)
            else:
                ok = configure(bus, FRESH_ID, target, args)
                if ok:
                    assigned_here += 1
                    if assigned_here == 1:
                        print()
                        print('  >>> For the first servo you must power off and on again, to confirm the ID was really saved <<<')
                        input('  Power off and on again, then press Enter to check... ')
                        if clean_ping(bus, target, tries=4):
                            print('  ID %d is still there after power off, EEPROM save works, going on.' % target)
                        else:
                            print('  !! No ping from ID %d after power off -- EEPROM did not save it.'
                                  % target)
                            print('     Fix this first, so the other %d are not done for nothing.' % (args.count - 1))
                            return 1
        if not ok:
            print('  This servo failed; check it and run again (servos already set up will not clash).')
            continue
        goto_center(bus, target, args)
        if target not in assigned:
            assigned.append(target)
        print('  This servo is done. Set up on the chain: %s' % sorted(assigned, reverse=True))

    print()
    print('All done. To check:')
    print('    python setup_ids.py --port %s --count %d --verify'
          % (args.port, args.count))
    return 0


def run_isolated(bus, args):
    """Old mode: connect each servo alone, IDs go up from start-id."""
    print('One-at-a-time mode: IDs from %d up to %d, unplug the previous servo each time.'
          % (args.start_id, args.start_id + args.count - 1))
    assigned = []
    for n in range(args.count):
        target = args.start_id + n
        print()
        print('--- servo %d/%d  ->  ID %d ---' % (n + 1, args.count, target))
        while True:
            input('  Connect only this servo (unplug all others), press Enter... ')
            if clean_ping(bus, FRESH_ID):
                break
            print('  !! No single reply on ID %d.' % FRESH_ID)
        if not configure(bus, FRESH_ID, target, args):
            continue
        goto_center(bus, target, args)
        assigned.append(target)
        print('  Unplug this servo, connect the next one.')
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', default='COM11')
    ap.add_argument('--baud', type=int, default=1000000)
    ap.add_argument('--count', type=int, default=15)
    ap.add_argument('--start-id', type=int, default=1,
                    help='only used in --isolated mode')
    ap.add_argument('--current', type=int, default=100,
                    help='goal current LSB (6.5mA/LSB), default 100 = 0.65A')
    ap.add_argument('--speed', type=int, default=100,
                    help='running speed LSB (0.732RPM/LSB), default 100')
    ap.add_argument('--accel', type=int, default=30)
    ap.add_argument('--multiturn', action='store_true',
                    help='set multi-turn absolute position (limits 0/0), default is single turn 0..4095')
    ap.add_argument('--isolated', action='store_true',
                    help='old mode: connect each servo alone, IDs go up')
    ap.add_argument('--center', metavar='IDS',
                    help='only move the given IDs to center to fit the servo horn, IDs unchanged. '
                         'e.g. --center 14,15 or --center all')
    ap.add_argument('--verify', action='store_true')
    args = ap.parse_args()

    try:
        bus = F.Bus(args.port, args.baud)
    except Exception as e:
        print('Could not open the serial port: %s' % e)
        print('(The FD desktop app holds the serial port while it is open, close it first)')
        return 1

    try:
        if args.verify:
            verify(bus, args.count)
            return 0
        if args.center:
            return run_center(bus, args)
        return run_isolated(bus, args) if args.isolated else run_chain(bus, args)
    except KeyboardInterrupt:
        print('\nInterrupted, broadcasting torque off to all servos...')
        try:
            bus.w8(F.BROADCAST, F.TORQUE, 0)
        except Exception:
            pass
        return 1
    finally:
        bus.close()


if __name__ == '__main__':
    sys.exit(main())

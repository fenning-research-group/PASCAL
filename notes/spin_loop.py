from tqdm import tqdm
import time
import asyncio


def spin_demo(repeat):
    for n in tqdm(range(repeat)):
        m.transfer(st2("A1"), sc())
        sc.set_rpm(rpm=5000, acceleration=1000)
        time.sleep(5)
        sc.stop()
        m.transfer(sc(), st2("A1"))
        time.sleep(1)
        g.movetoclear()
        time.sleep(1)


def solo_spincoat(steps):
    t0 = m.nist_time

    steps = np.array(steps)

    try:
        steps.shape[1]
        switch = 0
    except Exception:
        switch = 1
        pass

    if switch == 0:
        for step in steps:
            sc.set_rpm(rpm=step[0], acceleration=step[1])
            tnext = step[2]
            while m.nist_time - t0 < tnext:
                time.sleep(0.1)
            print(f"\t\t{t0-m.nist_time:.2f} finished step")
            sc.stop()
            print(f"\t{t0-m.nist_time:.2f} finished all spinspeed steps")

    if switch == 1:
        sc.set_rpm(rpm=steps[0], acceleration=steps[1])
        tnext = steps[2]
        while m.nist_time - t0 < tnext:
            time.sleep(0.1)
        print(f"\t\t{t0-m.nist_time:.2f} finished step")
        sc.stop()
        print(f"\t{t0-m.nist_time:.2f} finished all spinspeed steps")

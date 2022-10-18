from tqdm import tqdm
import time


def spin_demo(repeat):
    for n in tqdm(range(repeat)):
        m.transfer(st2("A1"), sc())
        sc.set_rpm(rpm=5000)
        time.sleep(5)
        sc.stop()
        m.transfer(sc(), st2("A1"))
        time.sleep(1)

def solo_spincoat(steps):
    t0 = m.nist_time
    for step in steps:
        sc.set_rpm(rpm=step["rpm"], acceleration=step["acceleration"])
        tnext += step["duration"]
        while self.maestro.nist_time - t0 < tnext:
            await asyncio.sleep(0.1)
        print(f"\t\t{t0-self.maestro.nist_time:.2f} finished step")
    self.spincoater.stop()
    print(f"\t{t0-self.maestro.nist_time:.2f} finished all spinspeed steps")
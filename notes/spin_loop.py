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

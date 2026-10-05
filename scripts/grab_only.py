import json
import os
import random
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kite as K


def main():
    chrome = K.find_chrome()
    port = 9500 + random.randint(0, 300)
    t, r = K.grab_ticket(chrome, port)
    one = K.exchange(t, r, "register")
    K.log("TICKET_JSON=" + json.dumps({"ticket": t, "randstr": r,
                                       "one": one, "port": port}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

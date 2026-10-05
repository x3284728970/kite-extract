import json
import os
import random
import string
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kite as K

MAIL_API = "https://api.mail.tm"
HANDOFF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "handoff.json")


def http(method, url, data=None, token=None, timeout=30):
    cmd = ["curl", "-s", "-m", str(timeout), "-X", method, url,
           "-H", "Content-Type: application/json"]
    if token:
        cmd += ["-H", "Authorization: Bearer " + token]
    if data is not None:
        cmd += ["-d", json.dumps(data)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except Exception:
        return {"__raw": r.stdout[:300]}


def make_mailbox():
    for _ in range(5):
        doms = http("GET", MAIL_API + "/domains")
        dom = doms["hydra:member"][0]["domain"]
        addr = "kiwi%s@%s" % ("".join(random.choices(
            string.ascii_lowercase + string.digits, k=9)), dom)
        pw = "Xx12345678abc"
        r = http("POST", MAIL_API + "/accounts", {"address": addr, "password": pw})
        if "id" in r:
            t = http("POST", MAIL_API + "/token", {"address": addr, "password": pw})
            if "token" in t:
                return addr, pw, t["token"]
    raise RuntimeError("邮箱创建失败")


def wait_code(mail_token, timeout=180):
    import re
    deadline = time.time() + timeout
    while time.time() < deadline:
        box = http("GET", MAIL_API + "/messages", token=mail_token)
        for m in box.get("hydra:member", []):
            full = http("GET", MAIL_API + "/messages/" + m["id"], token=mail_token)
            body = (full.get("text") or "") + " " + " ".join(full.get("html") or [])
            m2 = re.search(r"\b(\d{6})\b", body)
            if m2:
                return m2.group(1)
        time.sleep(6)
    return None


def main():
    """阶段一：拿票据 + 发码 + 收码，全部写进 handoff.json"""
    chrome = K.find_chrome()
    port = 9700 + random.randint(0, 200)

    addr, mpw, mtok = make_mailbox()
    K.log("临时邮箱: %s" % addr)
    pw = "KiProbe12345x"

    ticket, randstr = K.grab_ticket(chrome, port)
    one = K.exchange(ticket, randstr, "register")
    K.log("发码票据 ok len=%d" % len(one))

    r1 = K.http_json(K.API + "/auth/register",
                     {"email": addr, "password": pw,
                      "captcha_ticket": one, "randstr": randstr})
    K.log("发码: %s" % json.dumps(r1, ensure_ascii=False)[:180])
    if not r1.get("email_sent"):
        return 3

    code = wait_code(mtok)
    K.log("收到验证码: %s" % code)
    if not code:
        return 4

    # 再取一张注册票据，交给沙箱用
    t2, r2 = K.grab_ticket(chrome, port + 1)
    one2 = K.exchange(t2, r2, "register")
    K.log("交接票据 ok len=%d" % len(one2))

    data = {"email": addr, "mail_password": mpw, "password": pw,
            "code": code, "captcha_ticket": one2, "randstr": r2}
    with open(HANDOFF, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    K.log("已写 handoff.json")
    K.log("HANDOFF_JSON=" + json.dumps(data, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

import json
import os
import random
import re
import string
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kite as K

GM = "https://api.guerrillamail.com/ajax.php"


def gm(method, params, timeout=30):
    cmd = ["curl", "-s", "-m", str(timeout), GM + "?f=" + method + "&" + params]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
    try:
        return json.loads(r.stdout)
    except Exception:
        return {}


def make_mailbox():
    user = "kiwi" + "".join(random.choices(
        string.ascii_lowercase + string.digits, k=8))
    r = gm("set_email_user", "email_user=" + user)
    if "email_addr" not in r:
        r = gm("get_email_address", "")
    return r["email_addr"], r["sid_token"]


def wait_code(sid, timeout=220):
    deadline = time.time() + timeout
    seen = set()
    while time.time() < deadline:
        box = gm("check_email", "seq=0&sid_token=" + sid)
        for m in box.get("list", []):
            mid = m.get("mail_id")
            if mid in seen:
                continue
            seen.add(mid)
            full = gm("fetch_email", "email_id=%s&sid_token=%s" % (mid, sid))
            body = full.get("mail_body") or ""
            m2 = re.search(r"\b(\d{6})\b", body)
            if m2:
                return m2.group(1)
        time.sleep(6)
    return None


def main():
    chrome = K.find_chrome()
    addr, sid = make_mailbox()
    K.log("邮箱: %s" % addr)
    pw = "KiProbe12345x"

    port = 9600 + random.randint(0, 300)
    ticket, randstr = K.grab_ticket(chrome, port)
    one = K.exchange(ticket, randstr, "register")
    K.log("发码票据 ok")

    r1 = K.http_json(K.API + "/auth/register",
                     {"email": addr, "password": pw,
                      "captcha_ticket": one, "randstr": randstr})
    K.log("发码: %s" % json.dumps(r1, ensure_ascii=False)[:180])
    if not r1.get("email_sent"):
        return 3

    code = wait_code(sid)
    K.log("验证码: %s" % code)
    if not code:
        return 4

    r2 = K.http_json(K.API + "/auth/verify", {"email": addr, "code": code})
    K.log("verify: %s" % json.dumps(r2, ensure_ascii=False)[:250])
    if not (r2.get("code") == 0 or r2.get("access_token")
            or r2.get("refresh_token")):
        return 5
    K.log("*** 注册成功 ***")

    t2, r3 = K.grab_ticket(chrome, port + 1)
    one2 = K.exchange(t2, r3, "login")
    lg = K.http_json(K.API + "/auth/login",
                     {"email": addr, "password": pw,
                      "captcha_ticket": one2, "randstr": r3})
    K.log("登录: %s" % json.dumps(lg, ensure_ascii=False)[:250])
    rt = lg.get("refresh_token") or r2.get("refresh_token")
    if not rt:
        return 6
    try:
        cfg = json.loads(K.decrypt_config(rt).decode())
        obs = cfg.get("outbounds", [])
        K.log("*** outbounds=%d tags=%s" % (len(obs),
                                            [o.get("tag") for o in obs][:8]))
    except Exception as e:
        K.log("解密失败: %s" % str(e)[:150])
        return 7
    return 0


if __name__ == "__main__":
    sys.exit(main())

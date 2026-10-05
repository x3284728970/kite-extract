import json
import os
import random
import string
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kite as K

ACCT = "/tmp/kite_account.json"


def mk_email():
    tag = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    return "%s@outlook.com" % tag


def mk_pw():
    return "Ki" + "".join(random.choices(string.ascii_letters + string.digits, k=10)) + "9"


def show(tag, r):
    s = json.dumps(r, ensure_ascii=False) if isinstance(r, dict) else str(r)
    K.log("%-30s %s" % (tag, s[:220]))
    return r


def try_register(chrome, port, email, pw, booth):
    """booth: 取票据+交换，返回一次性票据"""
    ticket, randstr = K.grab_ticket(chrome, port)
    K.log("  ticket=%s randstr=%s" % (ticket[:36], randstr[:12]))
    one = K.exchange(ticket, randstr)
    return one, randstr, ticket


def main():
    chrome = K.find_chrome()
    K.log("chrome: %s" % chrome)
    port = 9400 + random.randint(0, 300)

    email, pw = mk_email(), mk_pw()
    K.log("email=%s pw=%s" % (email, pw))

    did = "".join(random.choices("0123456789abcdef", k=16))
    base = {"device_id": did, "device_type": "android", "device_model": "Pixel 7",
            "os_version": "14", "app_version": "2.1.0"}

    for attempt in range(3):
        K.log("--- 尝试 %d ---" % (attempt + 1))
        try:
            one, randstr, ticket = try_register(chrome, port + attempt, email, pw, None)
        except Exception as e:
            K.log("取票据失败: %s" % str(e)[:150])
            continue
        K.log("  one_ticket len=%d" % len(one))

        variants = [
            ("A captcha_ticket+randstr",
             {"email": email, "password": pw, "captcha_ticket": one, "randstr": randstr}),
            ("B verification obj",
             {"email": email, "password": pw,
              "verification": {"ticket": ticket, "randstr": randstr}}),
            ("C both",
             {"email": email, "password": pw, "captcha_ticket": one, "randstr": randstr,
              "verification": {"ticket": ticket, "randstr": randstr}}),
            ("D +device",
             {"email": email, "password": pw, "captcha_ticket": one, "randstr": randstr,
              "verification": {"ticket": ticket, "randstr": randstr}, **base}),
            ("E captcha nested",
             {"email": email, "password": pw,
              "captcha": {"ticket": one, "randstr": randstr}, **base}),
        ]
        for name, body in variants:
            try:
                r = K.http_json(K.API + "/auth/register", body)
            except Exception as e:
                K.log("%-28s ERR %s" % (name, str(e)[:100]))
                continue
            show(name, r)
            if r.get("code") == 0 or r.get("access_token") or r.get("refresh_token"):
                K.log("*** 注册成功 ***")
                with open(ACCT, "w") as f:
                    json.dump({"email": email, "password": pw, "resp": r}, f,
                              ensure_ascii=False, indent=1)
                return post_register(r)
            time.sleep(0.8)
        K.log("本轮未成功，换新票据重试")

    K.log("注册失败：所有变体都未通过")
    return 3


def post_register(reg):
    tok = reg.get("access_token") or ""
    hdr = {"Authorization": "Bearer " + tok} if tok else {}

    def call(method, path, body=None):
        return K.http_json(K.API + path, body) if body is not None else \
            K.http_json(K.API + path)

    for path in ["/auth/me", "/api/server/info", "/api/rewards/status"]:
        try:
            show("GET " + path, call("GET", path))
        except Exception as e:
            K.log("GET %-24s ERR %s" % (path, str(e)[:80]))

    for path in ["/auth/trial/claim", "/api/rewards/checkin"]:
        try:
            show("POST " + path, K.http_json(K.API + path, {}))
        except Exception as e:
            K.log("POST %-23s ERR %s" % (path, str(e)[:80]))

    rt = reg.get("refresh_token")
    if rt:
        try:
            cfg = json.loads(K.decrypt_config(rt).decode())
            obs = cfg.get("outbounds", [])
            K.log("refresh_token 解出 outbounds=%d tags=%s" % (len(obs), [o.get("tag") for o in obs]))
        except Exception as e:
            K.log("refresh_token 解密失败: %s" % str(e)[:120])
    return 0


if __name__ == "__main__":
    sys.exit(main())

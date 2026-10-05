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
ACCT = "/var/minis/workspace/kite/account.json"


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
    deadline = time.time() + timeout
    while time.time() < deadline:
        box = http("GET", MAIL_API + "/messages", token=mail_token)
        for m in box.get("hydra:member", []):
            full = http("GET", MAIL_API + "/messages/" + m["id"], token=mail_token)
            text = full.get("text") or ""
            html = " ".join(full.get("html") or [])
            body = text + " " + html
            import re
            for pat in [r"\b(\d{6})\b", r"code[^\d]{0,20}(\d{4,8})",
                        r"verification[^\d]{0,30}(\d{4,8})"]:
                m2 = re.search(pat, body, re.I)
                if m2:
                    return m2.group(1)
        time.sleep(6)
    return None


def main():
    chrome = K.find_chrome()
    K.log("chrome: %s" % chrome)
    port = 9500 + random.randint(0, 200)

    addr, mpw, mtok = make_mailbox()
    K.log("临时邮箱: %s" % addr)

    account = {"email": addr, "mail_password": mpw, "password": "KiProbe12345x"}
    pw = account["password"]

    ticket, randstr = K.grab_ticket(chrome, port)
    K.log("ticket=%s" % ticket[:40])
    one = K.exchange(ticket, randstr)
    K.log("one_ticket len=%d" % len(one))

    # 第一步：发验证码
    r1 = K.http_json(K.API + "/auth/register",
                     {"email": addr, "password": pw,
                      "captcha_ticket": one, "randstr": randstr})
    K.log("发码: %s" % json.dumps(r1, ensure_ascii=False)[:200])
    if not r1.get("email_sent"):
        K.log("发码失败，终止")
        return 3

    K.log("等验证码...")
    code = wait_code(mtok)
    if not code:
        K.log("没收到验证码")
        return 4
    K.log("收到验证码: %s" % code)
    account["code"] = code

    # 第二步：带码完成注册（穷举字段名）
    final = None
    for key in ["code", "verify_code", "email_code", "emailCode", "verification_code"]:
        body = {"email": addr, "password": pw, key: code}
        r2 = K.http_json(K.API + "/auth/register", body)
        K.log("注册[%s]: %s" % (key, json.dumps(r2, ensure_ascii=False)[:180]))
        if (r2.get("code") == 0 or r2.get("access_token")
                or r2.get("refresh_token") or "token" in json.dumps(r2)):
            final = r2
            account["field"] = key
            break
        time.sleep(1)

    if final:
        account["register_resp"] = final
        K.log("*** 注册成功 *** 字段=%s" % account.get("field"))
    with open(ACCT, "w") as f:
        json.dump(account, f, ensure_ascii=False, indent=1)

    # 第三步：登录并看节点
    try:
        t2, r2 = K.grab_ticket(chrome, port + 1)
        one2 = K.exchange(t2, r2)
    except Exception as e:
        K.log("二次取票据失败: %s" % str(e)[:100])
        one2 = None

    if one2:
        lg = K.http_json(K.API + "/auth/login",
                         {"email": addr, "password": pw,
                          "captcha_ticket": one2, "randstr": r2})
        K.log("登录: %s" % json.dumps(lg, ensure_ascii=False)[:250])
        rt = lg.get("refresh_token")
        if rt:
            try:
                cfg = json.loads(K.decrypt_config(rt).decode())
                obs = cfg.get("outbounds", [])
                K.log("*** outbounds=%d tags=%s" % (len(obs), [o.get("tag") for o in obs]))
                uris = []
                for o in obs:
                    if o.get("type") in ("vless", "tuic"):
                        try:
                            u = K.node_uri(o)
                            if u:
                                uris.append(u)
                        except Exception:
                            pass
                K.log("*** 节点数=%d" % len(uris))
                if uris:
                    open("/var/minis/workspace/kite/live_nodes.txt", "w").write("\n".join(uris))
                    K.log("已写入 live_nodes.txt")
            except Exception as e:
                K.log("解密失败: %s" % str(e)[:150])
        else:
            K.log("无明显节点字段，看 userinfo")
            ui = lg.get("userinfo")
            if ui:
                K.log("userinfo: %s" % json.dumps(ui, ensure_ascii=False)[:300])
    return 0


if __name__ == "__main__":
    sys.exit(main())

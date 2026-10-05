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
GIST_ID = "29ca02dc90c6157da30ca8ddfff95fe2"
GH_TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""


def sh(cmd, timeout=40):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.stdout


def gist_load():
    out = sh(["curl", "-s", "-m", "25",
              "-H", "Authorization: Bearer " + GH_TOKEN,
              "https://api.github.com/gists/" + GIST_ID])
    try:
        d = json.loads(out)
        content = d["files"]["state.json"]["content"]
        return json.loads(content)
    except Exception:
        return {}


def gist_save(obj):
    payload = json.dumps({"files": {"state.json": {"content": json.dumps(obj, ensure_ascii=False)}}})
    open("/tmp/gist_body.json", "w").write(payload)
    sh(["curl", "-s", "-m", "25", "-X", "PATCH",
        "-H", "Authorization: Bearer " + GH_TOKEN,
        "-H", "Content-Type: application/json",
        "https://api.github.com/gists/" + GIST_ID,
        "-d", "@/tmp/gist_body.json"])


def http(method, url, data=None, token=None, timeout=30):
    cmd = ["curl", "-s", "-m", str(timeout), "-X", method, url,
           "-H", "Content-Type: application/json"]
    if token:
        cmd += ["-H", "Authorization: Bearer " + token]
    if data is not None:
        cmd += ["-d", json.dumps(data)]
    try:
        return json.loads(sh(cmd, timeout + 10))
    except Exception:
        return {}


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


def wait_code(mail_token, timeout=200):
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


def stage_send(chrome):
    """阶段一：建箱 + 发码 + 收码，存进 gist"""
    port = 9700 + random.randint(0, 200)
    addr, mpw, mtok = make_mailbox()
    K.log("邮箱: %s" % addr)
    pw = "KiProbe12345x"

    ticket, randstr = K.grab_ticket(chrome, port)
    one = K.exchange(ticket, randstr, "register")
    r1 = K.http_json(K.API + "/auth/register",
                     {"email": addr, "password": pw,
                      "captcha_ticket": one, "randstr": randstr})
    K.log("发码: %s" % json.dumps(r1, ensure_ascii=False)[:180])
    if not r1.get("email_sent"):
        return 3

    code = wait_code(mtok)
    K.log("验证码: %s" % code)
    if not code:
        return 4

    st = gist_load()
    st["kite"] = {"email": addr, "mail_password": mpw, "password": pw,
                  "code": code, "sent_at": int(time.time()), "stage": "sent"}
    gist_save(st)
    K.log("已存 gist stage=sent")
    return 0

def stage_register(chrome):
    """阶段二：用存下的码走 /auth/verify 完成注册（无需票据）"""
    st = gist_load()
    k = st.get("kite") or {}
    if k.get("stage") != "sent":
        K.log("无待注册状态，先跑阶段一")
        return 5
    addr, pw, code = k["email"], k["password"], k["code"]
    waited = int(time.time()) - k.get("sent_at", 0)
    K.log("verify %s，距发码 %d 秒" % (addr, waited))

    r = K.http_json(K.API + "/auth/verify", {"email": addr, "code": code})
    K.log("verify: %s" % json.dumps(r, ensure_ascii=False)[:250])
    if r.get("code") == 0 or r.get("access_token") or r.get("refresh_token"):
        k.update({"stage": "registered", "resp": r})
        st["kite"] = k
        gist_save(st)
        K.log("*** 注册成功 ***")
        return inspect_nodes(chrome, addr, pw, 9900)
    return 6


def inspect_nodes(chrome, addr, pw, port):
    try:
        t, r = K.grab_ticket(chrome, port)
        one = K.exchange(t, r, "login")
    except Exception as e:
        K.log("登录取票据失败: %s" % str(e)[:100])
        return 7
    lg = K.http_json(K.API + "/auth/login",
                     {"email": addr, "password": pw,
                      "captcha_ticket": one, "randstr": r})
    K.log("登录: %s" % json.dumps(lg, ensure_ascii=False)[:250])
    rt = lg.get("refresh_token")
    if rt:
        try:
            cfg = json.loads(K.decrypt_config(rt).decode())
            obs = cfg.get("outbounds", [])
            K.log("*** outbounds=%d tags=%s" % (len(obs), [o.get("tag") for o in obs]))
        except Exception as e:
            K.log("解密失败: %s" % str(e)[:150])
    return 0


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "send"
    K.log("stage=%s" % stage)
    chrome = K.find_chrome()
    if stage == "send":
        return stage_send(chrome)
    return stage_register(chrome)


if __name__ == "__main__":
    sys.exit(main())

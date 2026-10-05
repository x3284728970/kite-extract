# kite-extract

Kite VPN 节点提取。GitHub Actions 每 8 小时运行一次 `scripts/kite.py`，产出加密节点清单 `output/kite.txt.enc`。

## 流程

1. 过腾讯天御验证码（playwright 无头 Chromium + `TJNCaptcha`，用 tdc 伪造参数换 ticket）
2. `POST /api/captcha/exchange`（scene=guest）→ 一次性票据
3. `POST /auth/guest/login` → `refresh_token`
4. 派生密钥 `PBKDF2-HMAC-SHA256(password, salt, 100000, 32)` → AES-256-GCM 解出节点清单
5. 用 `KITE_ENC_KEY` 对结果做 AES-256-GCM 加密，写 `output/kite.txt.enc` 并推送

## Secret

| 名称 | 说明 |
| --- | --- |
| `KITE_ENC_KEY` | 产物加密密钥，解密方需持有同一把 |

## 产物解密

`output/kite.txt.enc` 是 AES-256-GCM 密文，格式与脚本内 `decrypt_blob` / 加密段一致。持有 `KITE_ENC_KEY` 即可离线解出明文节点清单。

## 使用方

容器侧提取面板（第三台 kata）拉取该产物并解密，生成订阅。

## 定时

`.github/workflows/extract.yml`：`0 */8 * * *`（UTC），即北京时间 08:00 / 16:00 / 00:00，也可手动 `workflow_dispatch` 触发。

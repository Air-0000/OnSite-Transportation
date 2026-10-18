#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用系统 curl 驱动上传(绕过本机 OpenSSL 1.0.2 与 ngrok 边缘握手 SSLEOF 的问题)。
流程与 upload_submit.py 完全一致: 登录 -> 上传 zip -> 轮询状态页 -> 下载 score.csv。
依赖: curl 在 PATH 中(本机 Git Bash / 系统自带)。

用法:
  python upload_curl.py --zip <submit.zip> --user <账号> --password <密码> [--volume B] [--out score.csv]
  也可用环境变量 UPLOAD_USER / UPLOAD_PASS。不本地算分。
"""
import os
import re
import sys
import time
import subprocess

DEFAULT_URL = "https://physiocratic-babara-comely.ngrok-free.dev/accounts/upload/"

CURL = "curl"
# 清掉可能继承的代理(环境 HTTPS_PROXY=127.0.0.1:7877 会拒绝连接)
ENV = dict(os.environ)
ENV.pop("HTTPS_PROXY", None)
ENV.pop("HTTP_PROXY", None)
ENV.pop("https_proxy", None)
ENV.pop("http_proxy", None)
ENV["PYTHONIOENCODING"] = "utf-8"


def _curl(args, binary=False):
    """调用 curl, 返回 (stdout_text_or_bytes, )."""
    cmd = [CURL, "-sS"] + args
    p = subprocess.run(cmd, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        sys.stderr.write(p.stderr.decode("utf-8", "replace"))
        raise RuntimeError("curl 失败 rc=%d" % p.returncode)
    return p.stdout


def _get(url, jar, extra=None, effective=False):
    args = ["-c", jar, "-b", jar, "-L"]
    if effective:
        args += ["-w", "\n__EFF__%{url_effective}"]
    if extra:
        args += extra
    args += [url]
    return _curl(args)


def _post(url, jar, data=None, files=None, headers=None, effective=False):
    args = ["-c", jar, "-b", jar, "-L"]
    if effective:
        args += ["-w", "\n__EFF__%{url_effective}"]
    if headers:
        for k, v in headers.items():
            args += ["-H", "%s: %s" % (k, v)]
    if data:
        for k, v in data.items():
            args += ["-F", "%s=%s" % (k, v)]
    if files:
        for k, v in files.items():
            args += ["-F", "%s=@%s;type=application/zip" % (k, v)]
    args += [url]
    return _curl(args)


def _parse(html, patterns):
    out = {}
    for key, pat in patterns.items():
        m = re.search(pat, html)
        out[key] = m.group(1) if m else None
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True)
    ap.add_argument("--user", default=os.environ.get("UPLOAD_USER", ""))
    ap.add_argument("--password", default=os.environ.get("UPLOAD_PASS", ""))
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--volume", default="B")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    url = args.url
    user = args.user
    pw = args.password
    volume = args.volume
    zip_path = args.zip
    if not os.path.isfile(zip_path):
        print("用法: upload_curl.py --zip <submit.zip> --user <账号> --password <密码>")
        sys.exit(1)
    if not user or not pw:
        print("缺少账号密码: 用 --user/--password 或环境变量 UPLOAD_USER/UPLOAD_PASS")
        sys.exit(1)

    jar = os.path.join(os.path.dirname(os.path.abspath(zip_path)), ".curl_cookies.txt")

    # ① GET 上传页(未登录 -> 302 跳 login)
    print("[1/4] GET %s" % url)
    out = _get(url, jar, effective=True).decode("utf-8", "replace")
    html, eff = out.rsplit("__EFF__", 1) if "__EFF__" in out else (out, "")
    login = _parse(html, {
        "csrf": r'name="csrfmiddlewaretoken" value="([^"]+)"',
        "has_login": r'<title>(Login)</title>',
        "file_field": r'type="file"[^>]*name="([^"]+)"',
    })
    login_url = eff.strip() or url
    if login.get("has_login"):
        # ② 登录 POST
        assert login["csrf"], "登录页缺少 csrf token"
        print("[2/4] 登录中 (POST->%s)" % login_url)
        _post(login_url, jar, data={
            "csrfmiddlewaretoken": login["csrf"],
            "username": user,
            "password": pw,
            "next": url,
        })
        # ③ 登录后再 GET 上传页
        out = _get(url, jar, effective=True).decode("utf-8", "replace")
        html, eff = out.rsplit("__EFF__", 1) if "__EFF__" in out else (out, "")

    up = _parse(html, {
        "csrf": r'name="csrfmiddlewaretoken" value="([^"]+)"',
        "file_field": r'type="file"[^>]*name="([^"]+)"',
        "action": r'<form[^>]*action="([^"]*)"',
    })
    if not up.get("file_field"):
        print("登录失败或未取到上传表单。页面前 400 字符:")
        print(html[:400])
        sys.exit(1)

    file_field = up["file_field"]
    up_csrf = up.get("csrf")
    if not up_csrf:
        print("未取到上传表单 csrf。前 600 字符:")
        print(html[:600])
        sys.exit(1)
    action = up.get("action") or url
    if action.startswith("/"):
        from urllib.parse import urlparse
        p = urlparse(url)
        action = "%s://%s%s" % (p.scheme, p.netloc, action)

    # ④ 上传
    print("[3/4] 上传 %s (字段=%s, volume=%s, action=%s)" % (zip_path, file_field, volume, action))
    out = _post(action, jar,
                data={"csrfmiddlewaretoken": up_csrf, "volume": volume},
                files={file_field: zip_path},
                headers={"X-CSRFToken": up_csrf, "Referer": url},
                effective=True)
    out = out.decode("utf-8", "replace")
    html, eff = out.rsplit("__EFF__", 1) if "__EFF__" in out else (out, "")
    status_url = eff.strip() or url
    print("[4/4] 已提交, 轮询评分状态: %s" % status_url)

    out_path = args.out or os.path.join(os.path.dirname(os.path.abspath(zip_path)), "score.csv")
    downloaded = False
    for attempt in range(90):
        r = _get(status_url, jar).decode("utf-8", "replace")
        st = re.search(r"当前状态[:：]\s*([^<]+)", r)
        st = st.group(1).strip() if st else ""
        sc = re.search(r'href="([^"]*score\.csv)"', r)
        q = re.search(r"当前排队总人数[:：]\s*([^<]+)", r)
        q = q.group(1).strip() if q else ""
        print("   [%02d] 状态=%r 排队=%r score_link=%s" % (attempt, st, q, bool(sc)))
        if sc:
            dl = sc.group(1)
            if dl.startswith("/"):
                from urllib.parse import urlparse
                p = urlparse(status_url)
                dl = "%s://%s%s" % (p.scheme, p.netloc, dl)
            # 账号含空格(liu zhengyang) -> URL 必须 %20 转义, 否则 curl(3) URL rejected
            dl = dl.replace(" ", "%20")
            try:
                dr = _curl(["-c", jar, "-b", jar, dl])
                with open(out_path, "wb") as f:
                    f.write(dr)
                print("\n已下载 score.csv -> %s (%d 字节)" % (out_path, len(dr)))
                downloaded = True
                break
            except Exception as e:
                print("  找到 score.csv 但下载失败: %s" % e)
        if "完成" in st or "完成" in r or "失败" in st or "失败" in r:
            print("   评分完成但无 score.csv 链接, 页面片段:")
            print(re.sub(r"<[^>]+>", " ", r)[:400])
            break
        time.sleep(20)
    if not downloaded:
        print("\n未在限定时间内拿到 score.csv。可稍后手动访问状态页, 或重跑本脚本(会话可复用)。")
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()

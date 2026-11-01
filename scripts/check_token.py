#!/usr/bin/env python3
"""토큰 확인 테스트 (게시하지 않음, 읽기만 함).

실행: python3 scripts/check_token.py
- 토큰은 화면에 표시되지 않게 입력받고, 어디에도 저장하지 않습니다.
- 출력에 토큰 값은 절대 포함되지 않습니다.
"""
import getpass
import json
import os
import urllib.error
import urllib.parse
import urllib.request

API_VERSION = "v24.0"


def call(host, path, token, **params):
    params["access_token"] = token
    url = f"https://{host}/{API_VERSION}/{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return True, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            body = json.load(e)
            return False, body.get("error", body)
        except Exception:
            return False, {"message": f"HTTP {e.code}"}
    except Exception as e:  # 네트워크 오류 등
        return False, {"message": type(e).__name__}


def show(title, ok, data):
    mark = "✅ 성공" if ok else "❌ 실패"
    print(f"\n[{title}] {mark}")
    if ok:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(f"  메시지: {data.get('message')}")
        if data.get("code") is not None:
            print(f"  코드: {data.get('code')} / 타입: {data.get('type')}")


def main():
    token = os.environ.get("IG_ACCESS_TOKEN") or getpass.getpass(
        "액세스 토큰을 붙여넣고 Enter (화면에 표시되지 않습니다): "
    )
    token = token.strip()
    if not token:
        print("토큰이 입력되지 않았습니다.")
        return

    prefix = token[:4]
    kind = {
        "IGAA": "Instagram 로그인 토큰 (graph.instagram.com 용으로 보임)",
        "EAA": "Facebook 로그인/시스템 사용자 토큰 (graph.facebook.com 용으로 보임)",
    }
    guess = kind.get(prefix) or kind.get(prefix[:3]) or "형식을 알 수 없음"
    print(f"\n토큰 길이: {len(token)}자 / 앞 4글자: {prefix}… → {guess}")

    found = []

    # 1) graph.instagram.com
    ok, d = call("graph.instagram.com", "me", token,
                 fields="user_id,username,account_type,name")
    show("A. graph.instagram.com /me", ok, d)
    if ok:
        ig_id = d.get("user_id") or d.get("id")
        found.append(("graph.instagram.com", ig_id, d.get("username")))
        ok2, d2 = call("graph.instagram.com", f"{ig_id}/content_publishing_limit",
                       token, fields="config,quota_usage")
        show("A-2. 게시 한도 확인 (content_publish 권한 체크)", ok2, d2)

    # 2) graph.facebook.com
    ok, d = call("graph.facebook.com", "me", token, fields="id,name")
    show("B. graph.facebook.com /me", ok, d)
    if ok:
        okp, dp = call("graph.facebook.com", "me/permissions", token)
        if okp:
            granted = sorted(p["permission"] for p in dp.get("data", [])
                             if p.get("status") == "granted")
            need = ["instagram_basic", "instagram_content_publish",
                    "pages_show_list", "pages_read_engagement"]
            print("\n[B-1. 토큰에 들어 있는 권한]")
            for p in granted:
                print(f"  - {p}")
            missing = [p for p in need if p not in granted]
            print("  → 게시에 필요한데 빠진 권한:", ", ".join(missing) if missing else "없음 👍")
        else:
            show("B-1. 토큰 권한", okp, dp)

        okb, db = call("graph.facebook.com", "me/businesses", token, fields="id,name")
        show("B-1b. 연결된 비즈니스 포트폴리오", okb, db)

        ok2, d2 = call("graph.facebook.com", "debug_token", token, input_token=token)
        if ok2:
            info = d2.get("data", {})
            exp = info.get("expires_at")
            show("B-2. 토큰 정보", True, {
                "type": info.get("type"),
                "app": info.get("application"),
                "is_valid": info.get("is_valid"),
                "expires_at": "만료 없음" if exp in (0, None) else exp,
                "scopes": info.get("scopes"),
            })
        else:
            show("B-2. 토큰 정보", ok2, d2)

        ok3, d3 = call("graph.facebook.com", "me/accounts", token,
                       fields="name,instagram_business_account{id,username}")
        show("B-3. 연결된 페이지와 인스타 계정", ok3, d3)
        if ok3:
            for page in d3.get("data", []):
                iba = page.get("instagram_business_account")
                if iba:
                    found.append(("graph.facebook.com", iba.get("id"), iba.get("username")))
                    ok4, d4 = call("graph.facebook.com",
                                   f"{iba['id']}/content_publishing_limit", token,
                                   fields="config,quota_usage")
                    show("B-4. 게시 한도 확인 (content_publish 권한 체크)", ok4, d4)

        # 인스타 계정 ID로 직접 확인 (비즈니스 설정에서 확인한 ID)
        if not found:
            known_ig = "17841480053547861"
            ok5, d5 = call("graph.facebook.com", "1398394046693151", token,
                           fields="instagram_business_account,connected_instagram_account")
            show("B-5. 페이지에 연결된 인스타 (직접 조회)", ok5, d5)
            ok6, d6 = call("graph.facebook.com", known_ig, token,
                           fields="id,username,media_count")
            show("B-6. 인스타 계정 직접 조회", ok6, d6)
            if ok6:
                found.append(("graph.facebook.com", d6.get("id"), d6.get("username")))
                ok7, d7 = call("graph.facebook.com",
                               f"{known_ig}/content_publishing_limit", token,
                               fields="config,quota_usage")
                show("B-7. 게시 한도 확인 (content_publish 권한 체크)", ok7, d7)

    print("\n" + "=" * 50)
    if found:
        print("결론: 사용 가능한 조합")
        for host, ig_id, user in found:
            print(f"  - API 주소: {host} / 인스타 계정 ID: {ig_id} / @{user}")
    else:
        print("결론: 아직 인스타 계정 ID를 찾지 못했습니다. 이 화면을 캡처해서 보내주세요.")
    print("=" * 50)


if __name__ == "__main__":
    main()

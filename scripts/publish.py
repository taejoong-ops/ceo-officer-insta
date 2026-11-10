#!/usr/bin/env python3
"""@ceo_officer.kr 카드뉴스 자동 게시.

GitHub Actions에서 실행됩니다.
- posts/YYYY-MM-DD/ 의 01.png~ 이미지와 caption.txt 를 찾아
- PNG → JPG 변환 후 저장소에 커밋(공개 URL 생성)
- 인스타그램 캐러셀로 게시
- 성공하면 posts/done/ 으로 옮기고 logs/publish-log.md 에 기록

환경 변수
  IG_ACCESS_TOKEN  (GitHub Secret) 시스템 사용자 토큰
  IG_USER_ID       인스타 계정 ID
  GITHUB_REPOSITORY  owner/repo (Actions가 자동 설정)
  POST_DATE        게시할 날짜 (비우면 오늘, 한국시간)
  DRY_RUN          "true" 이면 게시하지 않고 점검만
"""
import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://graph.facebook.com/v24.0"
ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "posts"
DONE = POSTS / "done"
LOG = ROOT / "logs" / "publish-log.md"
KST = dt.timezone(dt.timedelta(hours=9))
IMAGE_EXTS = {".png", ".jpg", ".jpeg"}


class PublishError(Exception):
    pass


# ---------- Graph API ----------
def api(method, path, **params):
    params["access_token"] = os.environ["IG_ACCESS_TOKEN"]
    data = urllib.parse.urlencode(params).encode()
    if method == "GET":
        req = urllib.request.Request(f"{API}/{path}?{data.decode()}")
    else:
        req = urllib.request.Request(f"{API}/{path}", data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            err = json.load(e).get("error", {})
        except Exception:
            err = {"message": f"HTTP {e.code}"}
        raise PublishError(f"API 오류 ({path}): {err.get('message')} "
                           f"[code {err.get('code')}/{err.get('error_subcode')}]")


def wait_ready(container_id, label):
    for _ in range(30):  # 최대 약 5분
        status = api("GET", container_id, fields="status_code,status").get("status_code")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            detail = api("GET", container_id, fields="status").get("status")
            raise PublishError(f"{label} 처리 실패: {status} {detail}")
        time.sleep(10)
    raise PublishError(f"{label} 처리 시간 초과")


# ---------- 준비 ----------
def git(*args):
    subprocess.run(["git", *args], cwd=ROOT, check=True)


def find_images(folder):
    imgs = sorted(p for p in folder.iterdir()
                  if p.suffix.lower() in IMAGE_EXTS and p.parent == folder)
    if not imgs:
        raise PublishError(f"{folder.name} 에 이미지가 없습니다.")
    if len(imgs) > 10:
        raise PublishError(f"이미지가 {len(imgs)}장입니다. 캐러셀은 최대 10장입니다.")
    return imgs


def to_jpg(images, out_dir):
    from PIL import Image

    out_dir.mkdir(exist_ok=True)
    result = []
    for src in images:
        dst = out_dir / (src.stem + ".jpg")
        with Image.open(src) as im:
            im = im.convert("RGB")
            w, h = im.size
            ratio = w / h
            if not (0.8 <= ratio <= 1.91):
                raise PublishError(
                    f"{src.name} 비율 {w}x{h} 은 인스타 허용 범위(4:5 ~ 1.91:1)를 벗어납니다.")
            if w > 1440:
                im = im.resize((1440, round(h * 1440 / w)), Image.LANCZOS)
            im.save(dst, "JPEG", quality=92, optimize=True)
        result.append(dst)
    return result


def read_caption(folder):
    f = folder / "caption.txt"
    if not f.exists():
        raise PublishError(f"{folder.name}/caption.txt 가 없습니다.")
    text = f.read_text(encoding="utf-8").strip()
    if len(text) > 2200:
        raise PublishError(f"캡션이 {len(text)}자입니다. 최대 2200자입니다.")
    if text.count("#") > 30:
        raise PublishError("해시태그가 30개를 넘습니다.")
    return text


def write_log(date, status, detail):
    LOG.parent.mkdir(exist_ok=True)
    if not LOG.exists():
        LOG.write_text("# 게시 기록\n\n| 게시 날짜 | 실행 시각(KST) | 결과 | 내용 |\n|---|---|---|---|\n",
                       encoding="utf-8")
    now = dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    detail = str(detail).replace("|", "/").replace("\n", " ")
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"| {date} | {now} | {status} | {detail} |\n")


# ---------- 메인 ----------
def main():
    date = (os.environ.get("POST_DATE") or "").strip() or dt.datetime.now(KST).strftime("%Y-%m-%d")
    dry = os.environ.get("DRY_RUN", "").lower() == "true"
    folder = POSTS / date
    print(f"게시 날짜: {date} / 모드: {'점검만(DRY RUN)' if dry else '실제 게시'}")

    if not folder.is_dir():
        print(f"posts/{date} 폴더가 없습니다. 오늘은 게시할 것이 없어요. 종료합니다.")
        return 0

    ig_user = os.environ["IG_USER_ID"]
    repo = os.environ["GITHUB_REPOSITORY"]

    try:
        caption = read_caption(folder)
        images = find_images(folder)
        print(f"이미지 {len(images)}장, 캡션 {len(caption)}자")
        jpgs = to_jpg(images, folder / "jpg")

        # 공개 URL을 만들기 위해 JPG를 먼저 커밋/푸시
        git("add", str(folder / "jpg"))
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode != 0:
            git("commit", "-m", f"{date} JPG 변환")
            if not dry:
                git("push")
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        urls = [f"https://raw.githubusercontent.com/{repo}/{sha}/"
                f"{p.relative_to(ROOT).as_posix()}" for p in jpgs]

        if dry:
            # 토큰 점검 (읽기 전용 — 아무것도 게시하지 않음)
            acct = api("GET", ig_user, fields="username")
            quota = api("GET", f"{ig_user}/content_publishing_limit",
                        fields="quota_usage,config").get("data", [{}])[0]
            print(f"토큰 정상: @{acct.get('username')} 계정, "
                  f"오늘 게시 사용량 {quota.get('quota_usage')}/"
                  f"{quota.get('config', {}).get('quota_total')}")
            print("\n[점검 완료] 문제 없음. 실제 게시 시 사용할 이미지 주소:")
            for u in urls:
                print("  ", u)
            print("\n캡션 미리보기:\n" + caption[:300])
            return 0

        time.sleep(5)  # raw 주소 반영 대기
        if len(urls) == 1:
            cid = api("POST", f"{ig_user}/media", image_url=urls[0], caption=caption)["id"]
            wait_ready(cid, "이미지")
        else:
            children = []
            for i, u in enumerate(urls, 1):
                c = api("POST", f"{ig_user}/media", image_url=u, is_carousel_item="true")["id"]
                wait_ready(c, f"{i}번 카드")
                children.append(c)
                print(f"  {i}/{len(urls)} 카드 업로드 완료")
            cid = api("POST", f"{ig_user}/media", media_type="CAROUSEL",
                      children=",".join(children), caption=caption)["id"]
            wait_ready(cid, "캐러셀")

        media_id = api("POST", f"{ig_user}/media_publish", creation_id=cid)["id"]
        link = api("GET", media_id, fields="permalink").get("permalink", media_id)
        print(f"\n✅ 게시 완료: {link}")

        DONE.mkdir(exist_ok=True)
        git("mv", f"posts/{date}", f"posts/done/{date}")
        write_log(date, "✅ 성공", link)
        git("add", "-A", "logs", "posts")
        git("commit", "-m", f"{date} 게시 완료")
        git("push")
        return 0

    except PublishError as e:
        print(f"\n❌ 실패: {e}")
        if not dry:
            write_log(date, "❌ 실패", e)
            git("add", "logs")
            git("commit", "-m", f"{date} 게시 실패 기록")
            git("push")
        return 1


if __name__ == "__main__":
    sys.exit(main())

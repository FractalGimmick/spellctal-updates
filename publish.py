#!/usr/bin/env python3
"""Spellctal の更新告知スイッチ(latest.json を書き換えて push する)。

## 告知の順序(これを守らないと事故る)

1. GitHub でタグ → Windows インストーラができる
2. **BOOTH の商品ページに新しいインストーラを登録し、公開状態を確認する**
   (購入者側のダウンロードが新しいものになっていること。BOOTH は外から
   ファイルの版を機械的に確認できないため、ここは人の目で確認するしかない)
3. ここで初めて告知する = `./publish.py --version X.Y.Z --notes "..." --booth-ok`
4. 告知後に「まだ BOOTH に上がっていなかった」と分かったら `--version` を現行版に戻して取り下げる

`--booth-ok` は「②を済ませた」という人の宣言で、無いと書き換えない。
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "latest.json"
SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def main() -> int:
    ap = argparse.ArgumentParser(description="latest.json を更新して告知する")
    ap.add_argument("--version", required=True, help="告知する版(例: 0.7.0)")
    ap.add_argument(
        "--notes",
        default="",
        help=(
            "アプリ内バナーに1行で出る説明。"
            "空ならアプリ側が「BOOTH から最新版を入手できます。」を出す(推奨)"
        ),
    )
    ap.add_argument("--url", default=None, help="BOOTH 商品ページ(省略時は既存値を維持)")
    ap.add_argument(
        "--booth-ok",
        action="store_true",
        help="BOOTH に新バイナリを登録し公開を確認済み(必須)",
    )
    ap.add_argument("--no-push", action="store_true", help="commit までで push しない")
    ap.add_argument("--dry-run", action="store_true", help="書き換えずに内容を表示")
    ap.add_argument(
        "--force",
        action="store_true",
        help="内容が同じでも書き換えて published_at を更新する(通常は不要)",
    )
    args = ap.parse_args()

    if not SEMVER.match(args.version):
        print(f"ERROR: version が X.Y.Z 形式ではありません: {args.version}", file=sys.stderr)
        return 2

    if not args.booth_ok:
        print(
            "ERROR: --booth-ok がありません。\n"
            "  告知は「BOOTH の商品ページに新しいインストーラを登録し、購入者側の\n"
            "  ダウンロードが新しいものになっていることを確認した後」にだけ行います。\n"
            "  まだなら BOOTH の登録を先に済ませてください(順序を逆にすると\n"
            "  「ダウンロードしても古いまま」の通知が飛びます)。",
            file=sys.stderr,
        )
        return 3

    current = {}
    if MANIFEST.exists():
        current = json.loads(MANIFEST.read_text(encoding="utf-8"))

    # 「告知内容そのもの」(published_at を除く)が既に同じなら、コミットを作らない。
    # 同じ内容で何度でも安全に実行できるようにするため(CI からの再実行を含む)。
    # notes は「その回に出す文」をそのまま書く。省略(空)なら空で書く = 前回の文を
    # 引き継がない。アプリ側は notes が空なら「BOOTH から最新版を入手できます。」を
    # 自前で出す(src/update.ts の updateNoticeText)ので、ここでプレースホルダを
    # 焼き込む必要がない。以前は current を引き継いでいたため、最初の告知で入った
    # 「現在の最新版です。」が以後ずっとバナー本文として出続けていた。
    notes = args.notes.strip()
    wanted = {
        "version": args.version.lstrip("v"),
        "notes": notes,
        "url": args.url or current.get("url", ""),
    }
    same = all(current.get(k) == v for k, v in wanted.items())
    manifest = {
        **wanted,
        # 人が履歴を追うための記録。アプリは未知フィールドとして無視する。
        "published_at": (
            current.get("published_at", "")
            # --force は「内容が同じでもタイムスタンプを更新する」契約なので、
            # same でも今の時刻を書く(ここで force を見落とすと、書き換え内容が
            # 同一のまま git commit が空になり「失敗したように見える」)。
            if same and current.get("published_at") and not args.force
            else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        ),
    }
    text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    if not notes:
        print(
            "notes は空です。アプリのバナー本文は"
            "「BOOTH から最新版を入手できます。」になります。"
        )

    if same and not args.force:
        print(f"変更なし: すでに v{wanted['version']} を告知済みです(何もしません)。")
        print(text)
        return 0

    if args.dry_run:
        print(text)
        return 0

    MANIFEST.write_text(text, encoding="utf-8")
    print(text)

    if not (ROOT / ".git").exists():
        print("NOTE: git リポジトリではないので commit/push はしていません。latest.json を push してください。")
        return 0

    def git(*a: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True)

    git("add", "latest.json")
    r = git("commit", "-m", f"publish v{manifest['version']}")
    print(r.stdout.strip() or r.stderr.strip())
    if r.returncode != 0:
        print("ERROR: commit に失敗しました(告知は反映されていません)", file=sys.stderr)
        return 4
    if not args.no_push:
        p = git("push")
        print(p.stdout.strip() or p.stderr.strip())
        if p.returncode != 0:
            print("ERROR: push に失敗しました(コミットは作られましたが、告知はまだ反映されていません)", file=sys.stderr)
            return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

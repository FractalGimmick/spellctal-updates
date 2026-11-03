#!/usr/bin/env python3
"""publish.py の回帰テスト(stdlib のみ・依存なし)。

`publish.py` を一時ディレクトリへコピーして実行する。`ROOT` は
スクリプトの置き場所なので、`.git` が無い一時ディレクトリでは
commit/push を行わず `latest.json` だけを書く(= 書き換えロジックを
ネットワークも認証も無しで検証できる)。

実行: python3 -m unittest -v test_publish
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent / "publish.py"
PLACEHOLDER = "現在の最新版です。"
FALLBACK = "BOOTH から最新版を入手できます。"


class PublishTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        shutil.copy(SRC, self.root / "publish.py")
        self.manifest = self.root / "latest.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # ---- helpers ---------------------------------------------------------

    def run_publish(self, *args: str, booth_ok: bool = True):
        cmd = [sys.executable, str(self.root / "publish.py"), *args]
        if booth_ok:
            cmd.append("--booth-ok")
        return subprocess.run(cmd, cwd=self.root, capture_output=True, text=True)

    def seed(self, **fields) -> None:
        self.manifest.write_text(
            json.dumps(fields, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def read(self) -> dict:
        return json.loads(self.manifest.read_text(encoding="utf-8"))

    # ---- notes -----------------------------------------------------------

    def test_notes_are_not_inherited_when_omitted(self) -> None:
        """今回のバグの再発防止: 省略したら前回の文を引き継がず空で書く。

        以前は `args.notes or current.get("notes")` だったため、最初の告知で
        入れた「現在の最新版です。」が以後ずっとバナー本文として出続けた。
        """
        self.seed(version="1.0.0", notes=PLACEHOLDER, url="https://example.test/items/1")
        r = self.run_publish("--version", "1.0.1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read()["notes"], "")
        # 空にしたことを人が気づけるよう、実行ログにアプリ側の表示を出す
        self.assertIn(FALLBACK, r.stdout)

    def test_whitespace_only_notes_are_treated_as_empty(self) -> None:
        self.seed(version="1.0.0", notes=PLACEHOLDER, url="https://example.test/items/1")
        r = self.run_publish("--version", "1.0.1", "--notes", "   ")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read()["notes"], "")

    def test_notes_are_written_when_given(self) -> None:
        r = self.run_publish("--version", "1.0.1", "--notes", "字幕の区切りを改善しました。")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read()["notes"], "字幕の区切りを改善しました。")
        self.assertNotIn(FALLBACK, r.stdout)

    def test_url_is_kept_when_omitted(self) -> None:
        self.seed(version="1.0.0", notes="", url="https://example.test/items/9")
        self.run_publish("--version", "1.0.1")
        self.assertEqual(self.read()["url"], "https://example.test/items/9")

    # ---- 冪等性 -----------------------------------------------------------

    def test_same_content_is_a_noop(self) -> None:
        self.seed(
            version="1.0.1",
            notes="",
            url="https://example.test/items/1",
            published_at="2026-01-01T00:00:00Z",
        )
        before = self.manifest.read_text(encoding="utf-8")
        r = self.run_publish("--version", "1.0.1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("変更なし", r.stdout)
        # 本文も published_at も動かない
        self.assertEqual(self.manifest.read_text(encoding="utf-8"), before)

    def test_force_updates_the_timestamp_only(self) -> None:
        self.seed(
            version="1.0.1",
            notes="",
            url="https://example.test/items/1",
            published_at="2026-01-01T00:00:00Z",
        )
        r = self.run_publish("--version", "1.0.1", "--force")
        self.assertEqual(r.returncode, 0, r.stderr)
        d = self.read()
        self.assertEqual(d["version"], "1.0.1")
        self.assertEqual(d["notes"], "")
        self.assertNotEqual(d["published_at"], "2026-01-01T00:00:00Z")

    # ---- 安全側の拒否 -----------------------------------------------------

    def test_refuses_without_booth_ok(self) -> None:
        r = self.run_publish("--version", "1.0.1", booth_ok=False)
        self.assertEqual(r.returncode, 3)
        self.assertFalse(self.manifest.exists(), "拒否したのに manifest を書いている")

    def test_rejects_malformed_version(self) -> None:
        for bad in ("1.1", "v1.0", "1.0.1.0", "latest"):
            with self.subTest(version=bad):
                r = self.run_publish("--version", bad)
                self.assertEqual(r.returncode, 2)
                self.assertFalse(self.manifest.exists(), "不正な版なのに manifest を書いている")

    def test_v_prefix_is_normalised(self) -> None:
        r = self.run_publish("--version", "v1.0.1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read()["version"], "1.0.1")


if __name__ == "__main__":
    unittest.main()

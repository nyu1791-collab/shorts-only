import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from shorts_only import ffmpeg_recipes as fr
from shorts_only.standalone import hook_title, write_hook


class Hook(unittest.TestCase):
    def test_generic_titles_get_no_banner(self):
        profile = {"name": "配信者A"}
        self.assertEqual(hook_title({"title": "配信者A ショート 2"}, profile), "")
        self.assertEqual(hook_title({"title": "切り抜き 3"}, profile), "")
        self.assertEqual(hook_title({"title": "  ボス戦で  奇跡の逆転 "}, profile), "ボス戦で 奇跡の逆転")
        self.assertEqual(hook_title({"title": "ボス戦"}, {**profile, "hook_banner": "off"}), "")

    def test_hook_file_escapes_override_braces(self):
        with tempfile.TemporaryDirectory() as folder:
            path = write_hook(Path(folder) / "hook.ass", "罠{\\b1}", 720, 1280, {"accent_color": "#66D9EF"})
            text = path.read_text(encoding="utf-8")
            self.assertIn("罠（＼b1）", text)
            self.assertIn("&H00EFD966", text)  # #66D9EF in ASS byte order

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is not installed")
    def test_banner_and_progress_bar_render(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=640x360:d=4:r=25",
                            "-f", "lavfi", "-i", "sine=f=300:d=4", "-shortest", str(folder / "in.mp4")], check=True)
            write_hook(folder / "hook.ass", "ボス戦で奇跡の逆転", 360, 640, {})
            vf = (fr.fit_frame(360, 640) + ",ass=hook.ass"
                  + ",drawbox=x=0:y=ih-6:w='iw*t/4.000':h=6:color=0xFFE568@0.95:t=fill")
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", "in.mp4", "-vf", vf,
                            *fr.delivery_args("draft"), "out.mp4"], cwd=folder, check=True)
            self.assertGreater((folder / "out.mp4").stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()

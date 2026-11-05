import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import install


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dest = Path(self.temp.name) / 'skills' / install.NAME

    def test_dry_run_does_not_create_directories(self):
        result = install.install(ROOT, self.dest, dry_run=True)
        self.assertEqual(result['action'], 'install')
        self.assertFalse(self.dest.parent.exists())

    def test_fresh_install_contains_runtime_not_repository_metadata(self):
        install.install(ROOT, self.dest)
        self.assertEqual((self.dest / 'SKILL.md').read_bytes(), (ROOT / 'SKILL.md').read_bytes())
        self.assertTrue((self.dest / 'scripts/studio.py').is_file())
        self.assertTrue((self.dest / 'LICENSE').is_file())
        self.assertFalse((self.dest / '.git').exists())
        self.assertFalse((self.dest / 'tests').exists())

    def test_replace_preserves_original_and_refuses_implicit_overwrite(self):
        install.install(ROOT, self.dest)
        marker = self.dest / 'old-setting.txt'
        marker.write_text('keep me', encoding='utf-8')
        with self.assertRaises(ValueError):
            install.install(ROOT, self.dest)
        result = install.install(ROOT, self.dest, replace=True)
        self.assertEqual((Path(result['backup']) / marker.name).read_text(), 'keep me')
        self.assertFalse(marker.exists())

    def test_copy_failure_leaves_original_untouched(self):
        install.install(ROOT, self.dest)
        original = (self.dest / 'SKILL.md').read_bytes()
        with patch.object(install.shutil, 'copytree', side_effect=OSError('simulated full disk')):
            with self.assertRaises(OSError):
                install.install(ROOT, self.dest, replace=True)
        self.assertEqual((self.dest / 'SKILL.md').read_bytes(), original)

    def test_no_overlapping_directories_or_non_skill_replacement(self):
        for dest in [ROOT, ROOT / 'nested', ROOT.parent]:
            with self.subTest(dest=dest), self.assertRaises(ValueError):
                install.install(ROOT, dest, replace=True, dry_run=True)
        self.dest.mkdir(parents=True)
        with self.assertRaises(ValueError):
            install.install(ROOT, self.dest, replace=True)

    def test_default_respects_codex_home(self):
        with patch.dict(install.os.environ, {'CODEX_HOME': self.temp.name}):
            self.assertEqual(install.default_destination(), Path(self.temp.name) / 'skills' / install.NAME)


if __name__ == '__main__':
    unittest.main()

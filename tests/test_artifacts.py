from pathlib import Path
import tempfile
import unittest

from stack.artifacts import sha256, upgrade


class ArtifactMigrationTests(unittest.TestCase):
    def test_reproducible_across_checkout_line_endings_and_preserves_source(self):
        # A tiny converter exercising the real wrapper's filesystem/UUID contract.
        converter = (
            "from pathlib import Path\nimport uuid\nimport os\n"
            "def upgrade(source, output):\n"
            "    template = Path(__file__).parent / 'chat_templates/qwen3_8.jinja'\n"
            "    output.write_bytes(uuid.uuid4().bytes + source.read_bytes() + template.read_bytes())\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "old.ninfer"
            source.write_bytes(b"original weights\x00\xff")
            digest = sha256(source)
            results = []
            for name, eol in (("lf", "\n"), ("crlf", "\r\n")):
                tools = root / name
                (tools / "chat_templates").mkdir(parents=True)
                (tools / "upgrade_ninfer_v2_to_v3.py").write_bytes(converter.replace("\n", eol).encode())
                for template in ("qwen3_6.jinja", "qwen3_8.jinja"):
                    (tools / "chat_templates" / template).write_bytes(("template" + eol).encode())
                output = root / (name + ".ninfer")
                upgrade(source, output, tools, digest)
                results.append(output.read_bytes())
                with self.assertRaises(FileExistsError):
                    upgrade(source, output, tools, digest)
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    upgrade(source, root / "bad.ninfer", tools, "0" * 64)
                self.assertFalse((root / "bad.ninfer").exists())
            self.assertEqual(results[0], results[1])
            self.assertEqual(sha256(source), digest)

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from utils import format_prompt, get_memory_info, get_memory_placeholders


class PromptUtilsTests(unittest.TestCase):
    def test_unknown_placeholder_is_preserved(self):
        self.assertEqual(
            format_prompt("内存 {memory} / {unknown}", {"memory": "1GB"}),
            "内存 1GB / {unknown}",
        )

    @patch("psutil.virtual_memory")
    def test_memory_placeholders(self, virtual_memory):
        gib = 1024**3
        virtual_memory.return_value = SimpleNamespace(total=16 * gib, available=6 * gib)

        values = get_memory_placeholders()

        self.assertEqual(values["used_memory"], "10.0GB")
        self.assertEqual(values["available_memory"], "6.0GB")
        self.assertEqual(values["total_memory"], "16.0GB")
        self.assertEqual(values["memory_percent"], "62.5%")
        self.assertEqual(values["memory"], "10.0GB/16.0GB(62.5%)")
        self.assertEqual(get_memory_info(), values["memory"])


if __name__ == "__main__":
    unittest.main()

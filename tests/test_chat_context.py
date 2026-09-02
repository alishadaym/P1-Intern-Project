import unittest

from app import build_mall_context


class ChatContextTests(unittest.TestCase):
    def test_build_mall_context_mentions_dpulze_and_mall_specific_details(self):
        context = build_mall_context()
        lowered = context.lower()
        self.assertIn("dpulze", lowered)
        self.assertIn("this mall", lowered)
        self.assertIn("facility", lowered)
        self.assertIn("description", lowered)
        self.assertIn("products", lowered)


if __name__ == "__main__":
    unittest.main()

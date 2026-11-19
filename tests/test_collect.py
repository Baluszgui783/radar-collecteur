import unittest
from unittest.mock import patch
import collect

class Collection(unittest.TestCase):
    def test_domain(self):
        self.assertTrue(collect.owned("https://help.example.org/a","example.org"))
        self.assertFalse(collect.owned("https://example.org.example.net/a","example.org"))
    def test_api_down(self):
        with patch("collect.fetch",side_effect=TimeoutError), self.assertRaises(TimeoutError):
            collect.collect({}, "2026-01-01")
    def test_text(self):
        page=collect.Page("<p>Test &amp; texte</p><script>private</script>")
        self.assertEqual(page.text,"Test & texte")
    def test_empty_batch_fails(self):
        with patch("collect.discover",return_value=[]), self.assertRaises(collect.Closed):
            collect.collect({}, "2026-01-01")

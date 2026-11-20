import json
from pathlib import Path
import unittest
from unittest.mock import patch
import collect

class Collection(unittest.TestCase):
    def test_domain(self):
        self.assertTrue(collect.owned("https://help.example.org/a","example.org"))
        self.assertFalse(collect.owned("https://example.org.example.net/a","example.org"))
    def test_api_down(self):
        with patch("collect.fetch",side_effect=TimeoutError), self.assertRaises(TimeoutError):
            collect.collect({"watch": [{"siren": "000000000"}]}, "2026-01-01")
    def test_text(self):
        page=collect.Page("<p>Test &amp; texte</p><script>private</script>")
        self.assertEqual(page.text,"Test & texte")
    def test_empty_batch_fails(self):
        with patch("collect.fetch") as fetch, self.assertRaises(collect.Closed):
            collect.collect({"watch": [], "discovery_domains": {"unused.invalid": {}}}, "2026-01-01")
        fetch.assert_not_called()

    def test_main_verifies_watch_and_posts_one_company_without_discovery(self):
        fixture = Path(__file__).resolve().parents[1] / "fixtures" / "config.example.json"
        config = json.loads(fixture.read_text(encoding="utf-8"))
        config["discovery_domains"] = {"unused.invalid": {}}
        candidate, = config["watch"]
        signal, = candidate["signals"]
        destination = "https://radar.invalid/api/ingest"
        environment = {
            "SOURCE_CONFIG": json.dumps(config),
            "DEPOSIT_URL": destination,
            "SITE_SERVICE": "fictif-service",
            "DEPOSIT_KEY": "fictif-depot",
        }
        registry_url = collect.API + "?q=000000000&per_page=1&minimal=true&include=siege"
        registry_row = {
            "siren": candidate["siren"], "nom_complet": "Nom vérifié fictif",
            "etat_administratif": "A", "statut_diffusion": "O",
            "siege": {"statut_diffusion_etablissement": "O"},
            "opposition_diffusion_commerciale": False,
        }
        reads = {
            registry_url: json.dumps({"results": [registry_row]}).encode(),
            "https://example.org/robots.txt": b"User-agent: *\nAllow: /",
            candidate["legal_url"]: candidate["legal_snippet"].encode(),
            signal["url"]: signal["term"].encode(),
        }
        posts = []

        def fake_fetch(url, body=None, headers=None):
            if body is None:
                return reads[url]
            self.assertEqual(url, destination)
            posts.append(json.loads(body))
            return b'{"replayed": false}'

        with (
            patch.object(collect.os, "environ", environment),
            patch.object(collect, "robots", {}),
            patch.object(collect, "cache", {}),
            patch.object(collect, "fetch", side_effect=fake_fetch),
            patch.object(collect, "discover", side_effect=AssertionError("discovery called")) as discover,
        ):
            collect.main()

        discover.assert_not_called()
        self.assertEqual(len(posts), 1)
        company, = posts[0]["companies"]
        self.assertEqual(company["siren"], candidate["siren"])
        self.assertEqual(company["legal_name"], registry_row["nom_complet"])
        self.assertEqual(company["signals"][0]["url"], signal["url"])
        self.assertEqual(posts[0]["withdrawn"], [])

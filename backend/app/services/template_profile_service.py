"""
Versioned indicator stacks + rulebooks.

Files live under app/templates/:
  indicator_stack_v{N}.json
  rulebook_v{N}.json
  active_profile.json

Adding a new version:
  1. Copy indicator_stack_v1.json -> indicator_stack_v2.json and edit.
  2. Copy rulebook_v1.json -> rulebook_v2.json; point engine if needed.
  3. Admin activates via POST /api/admin/templates/activate
  4. Mobile clients poll GET /api/templates/active and show install checklist.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.logging import configure_logging

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


class TemplateProfileService:
    def __init__(self) -> None:
        self.logger = configure_logging(__name__)
        self._cache: dict[str, Any] = {}

    def _read(self, name: str) -> dict[str, Any]:
        path = TEMPLATES_DIR / name
        if not path.exists():
            raise FileNotFoundError(f"Template missing: {path}")
        with path.open() as f:
            return json.load(f)

    def _write(self, name: str, data: dict[str, Any]) -> None:
        path = TEMPLATES_DIR / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            json.dump(data, f, indent=2)

    def get_active_pointer(self) -> dict[str, str]:
        try:
            return self._read("active_profile.json")
        except FileNotFoundError:
            return {
                "indicator_stack_version": "v1",
                "rulebook_version": "v1",
            }

    def list_indicator_stacks(self) -> list[dict[str, Any]]:
        out = []
        for p in sorted(TEMPLATES_DIR.glob("indicator_stack_v*.json")):
            data = json.loads(p.read_text())
            out.append(
                {
                    "version": data.get("version"),
                    "title": data.get("title"),
                    "status": data.get("status"),
                    "install_steps": len(data.get("install_order") or []),
                    "file": p.name,
                }
            )
        return out

    def list_rulebooks(self) -> list[dict[str, Any]]:
        out = []
        for p in sorted(TEMPLATES_DIR.glob("rulebook_v*.json")):
            data = json.loads(p.read_text())
            out.append(
                {
                    "version": data.get("version"),
                    "title": data.get("title"),
                    "status": data.get("status"),
                    "indicator_stack_version": data.get("indicator_stack_version"),
                    "engine": data.get("engine"),
                    "file": p.name,
                }
            )
        return out

    def get_indicator_stack(self, version: str) -> dict[str, Any]:
        ver = version.lstrip("v")
        return self._read(f"indicator_stack_v{ver}.json")

    def get_rulebook(self, version: str) -> dict[str, Any]:
        ver = version.lstrip("v")
        return self._read(f"rulebook_v{ver}.json")

    def get_active_bundle(self) -> dict[str, Any]:
        ptr = self.get_active_pointer()
        stack_v = ptr.get("indicator_stack_version", "v1")
        book_v = ptr.get("rulebook_version", "v1")
        stack = self.get_indicator_stack(stack_v)
        book = self.get_rulebook(book_v)
        return {
            "indicator_stack_version": stack_v,
            "rulebook_version": book_v,
            "indicator_stack": stack,
            "rulebook": book,
            "updated_at": ptr.get("updated_at"),
        }

    def activate(self, indicator_stack_version: str, rulebook_version: str) -> dict[str, Any]:
        # Validate files exist
        self.get_indicator_stack(indicator_stack_version)
        self.get_rulebook(rulebook_version)
        ptr = {
            "indicator_stack_version": indicator_stack_version
            if indicator_stack_version.startswith("v")
            else f"v{indicator_stack_version}",
            "rulebook_version": rulebook_version
            if rulebook_version.startswith("v")
            else f"v{rulebook_version}",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        # normalize
        if not ptr["indicator_stack_version"].startswith("v"):
            ptr["indicator_stack_version"] = "v" + ptr["indicator_stack_version"]
        if not ptr["rulebook_version"].startswith("v"):
            ptr["rulebook_version"] = "v" + ptr["rulebook_version"]
        self._write("active_profile.json", ptr)
        self._cache.clear()
        self.logger.info("Activated profile %s", ptr)
        return ptr

    def vision_config_for_brain(self) -> dict[str, Any]:
        """
        Shape expected by BrainCVService: merge active indicator stack into
        the historic colors_config.json structure.
        """
        bundle = self.get_active_bundle()
        stack = bundle["indicator_stack"]
        return {
            "config_version": f"AEGIS_STACK_{bundle['indicator_stack_version']}_RULE_{bundle['rulebook_version']}",
            "description": stack.get("description"),
            "image_profile": {
                "source": stack.get("title"),
                "template": stack.get("title"),
                "theme": stack.get("theme"),
                "timeframe": stack.get("timeframe"),
            },
            "color_space": stack.get("color_space", "HSV"),
            "global_tolerance": stack.get("global_tolerance", {}),
            "roi": stack.get("roi", {}),
            "indicators": stack.get("indicators", {}),
            "price_panel_indicators": stack.get("price_panel_indicators", {}),
            "candle_colors": stack.get("candle_colors", {}),
            "history": stack.get("history", {}),
            "noise_filter": stack.get("noise_filter", {}),
            "rulebook_version": bundle["rulebook_version"],
            "indicator_stack_version": bundle["indicator_stack_version"],
        }

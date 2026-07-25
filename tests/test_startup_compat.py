import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import startup_compat


class StartupCompatibilityTests(unittest.TestCase):
    def test_streamlit_requires_the_current_analysis_revision_marker(self):
        marker = "ANALYSIS_CORE_REVISION_20260725_RELIABLE_REVIEW"
        source = (
            Path(__file__).resolve().parents[1] / "streamlit_app.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        exports = None
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if any(
                isinstance(target, ast.Name)
                and target.id == "_ANALYSIS_CORE_EXPORTS"
                for target in node.targets
            ):
                exports = ast.literal_eval(node.value)
                break

        self.assertIsNotNone(exports)
        self.assertIn(marker, exports)
        self.assertTrue(
            hasattr(
                startup_compat.importlib.import_module("analysis_core"),
                marker,
            )
        )

    def test_current_module_is_returned_without_reload(self):
        current = SimpleNamespace(required_export=object())

        with (
            patch.object(
                startup_compat.importlib,
                "import_module",
                return_value=current,
            ),
            patch.object(startup_compat.importlib, "reload") as reload_module,
        ):
            resolved = startup_compat.import_module_with_exports(
                "analysis_core",
                ("required_export",),
            )

        self.assertIs(resolved, current)
        reload_module.assert_not_called()

    def test_stale_module_is_reloaded_when_an_export_is_missing(self):
        stale = SimpleNamespace()
        refreshed = SimpleNamespace(required_export=object())

        with (
            patch.object(
                startup_compat.importlib,
                "import_module",
                return_value=stale,
            ),
            patch.object(
                startup_compat.importlib,
                "reload",
                return_value=refreshed,
            ) as reload_module,
            patch.object(
                startup_compat.importlib,
                "invalidate_caches",
            ) as invalidate_caches,
        ):
            resolved = startup_compat.import_module_with_exports(
                "analysis_core",
                ("required_export",),
            )

        self.assertIs(resolved, refreshed)
        invalidate_caches.assert_called_once_with()
        reload_module.assert_called_once_with(stale)

    def test_revision_marker_reloads_same_shape_stale_module_once(self):
        stale = SimpleNamespace(analyze_report=object())
        refreshed = SimpleNamespace(
            analyze_report=object(),
            ANALYSIS_CORE_REVISION_20260725_RELIABLE_REVIEW=True,
        )

        with (
            patch.object(
                startup_compat.importlib,
                "import_module",
                return_value=stale,
            ),
            patch.object(
                startup_compat.importlib,
                "reload",
                return_value=refreshed,
            ) as reload_module,
            patch.object(
                startup_compat.importlib,
                "invalidate_caches",
            ) as invalidate_caches,
        ):
            resolved = startup_compat.import_module_with_exports(
                "analysis_core",
                (
                    "analyze_report",
                    "ANALYSIS_CORE_REVISION_20260725_RELIABLE_REVIEW",
                ),
            )

        self.assertIs(resolved, refreshed)
        self.assertTrue(
            resolved.ANALYSIS_CORE_REVISION_20260725_RELIABLE_REVIEW
        )
        invalidate_caches.assert_called_once_with()
        reload_module.assert_called_once_with(stale)

    def test_missing_export_after_reload_has_operator_guidance(self):
        stale = SimpleNamespace()

        with (
            patch.object(
                startup_compat.importlib,
                "import_module",
                return_value=stale,
            ),
            patch.object(
                startup_compat.importlib,
                "reload",
                return_value=stale,
            ),
        ):
            with self.assertRaisesRegex(
                ImportError,
                "Reboot the Streamlit app",
            ):
                startup_compat.import_module_with_exports(
                    "analysis_core",
                    ("ANALYST_MODELS",),
                )


if __name__ == "__main__":
    unittest.main()

"""Keep application policy independent from concrete infrastructure adapters."""
import ast
from pathlib import Path
import sys
import unittest


class ArchitectureTests(unittest.TestCase):
    def test_core_dependency_direction(self):
        root = Path(__file__).resolve().parents[1] / 'evidence_agent'
        allowed = {'domain': set(), 'ports': {'domain'}, 'service': {'domain', 'ports'}}
        for module, dependencies in allowed.items():
            tree = ast.parse((root / f'{module}.py').read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                imports = []
                if isinstance(node, ast.Import):
                    imports = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        self.assertEqual(node.level, 1, module)
                        self.assertIn(node.module, dependencies, module)
                    else:
                        imports = [node.module or '']
                for name in imports:
                    with self.subTest(module=module, dependency=name):
                        self.assertIn(name.split('.')[0], sys.stdlib_module_names)

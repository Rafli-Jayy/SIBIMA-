"""One-time optional compatibility update for the old Patch 3 allowlist test.

Changes ONLY tests/test_ai_patch3_readonly.py and creates a .bak file.
Does not touch application files, DB, or .env.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / 'tests' / 'test_ai_patch3_readonly.py'
if not path.exists():
    raise SystemExit('Tes Patch 3 lama tidak ditemukan; tidak ada file yang diubah.')
code = path.read_text(encoding='utf-8')
if 'PATCH4F1_EXTRA_ROLE_TOOLS' in code:
    print('Tes sudah mendukung Patch 4F.1; tidak perlu diubah.')
    raise SystemExit(0)

if 'from app.services.ai_tool_controller import AIToolController, ROLE_TO_TOOLS' not in code:
    raise SystemExit('Struktur import tes berbeda. Tidak ada file yang diubah.')

anchor_old = '        assert {item["name"] for item in control.declarations()} == set(allowed)'
if anchor_old in code:
    replacement = '''        declared = {item["name"] for item in control.declarations()}
        expected = set(allowed) | set(EXTRA_ROLE_TO_TOOLS[role])  # PATCH4F1_EXTRA_ROLE_TOOLS
        if control.rag_tool is not None:
            expected.add("search_knowledge_base")
        assert declared == expected'''
    code = code.replace(anchor_old, replacement, 1)
elif '        expected = set(allowed)' in code and '        assert declared == expected' in code:
    code = code.replace('        expected = set(allowed)',
                        '        expected = set(allowed) | set(EXTRA_ROLE_TO_TOOLS[role])  # PATCH4F1_EXTRA_ROLE_TOOLS', 1)
else:
    raise SystemExit('Pola pemeriksaan tes tidak dikenali. Tidak ada file yang diubah.')

code = code.replace('from app.services.ai_tool_controller import AIToolController, ROLE_TO_TOOLS',
                    'from app.services.ai_tool_controller import AIToolController, ROLE_TO_TOOLS, EXTRA_ROLE_TO_TOOLS', 1)
backup = path.with_suffix('.py.bak')
backup.write_text(path.read_text(encoding='utf-8'), encoding='utf-8')
path.write_text(code, encoding='utf-8')
print('BERHASIL: tes allowlist lama diselaraskan. Backup:', backup.name)

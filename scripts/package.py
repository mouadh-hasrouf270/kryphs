from pathlib import Path
import zipfile
root=Path(__file__).resolve().parents[1]
output=root.parent/'CreativeManager-standalone.zip'
excluded={'.venv','node_modules','__pycache__','.git','.pytest_cache','.ruff_cache','dist','media','staticfiles','test-results','playwright-report','backups','mail','local-logs'}
with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(root.rglob('*')):
        relative=path.relative_to(root)
        if not path.is_file() or any(part in excluded for part in relative.parts):continue
        if path.name=='.env' or '.sqlite3' in path.name or path.suffix in ['.pyc','.log'] or path.name in ['.coverage','tsconfig.tsbuildinfo']:continue
        archive.write(path,'creative-manager/'+relative.as_posix())
print(output)

from pathlib import Path
import hashlib,json,shutil
sources=[Path(r'D:\Codex\Documents\Train\controller_extended_20261014'),Path(r'D:\Codex\Documents\Train\controller_pressure_20261014')]
repo=Path(r'F:\列车大创xmc\multi-agent\traffic_rl_project')
archive=repo/'outputs/sim_validation/phys_validation/controller_repair_20261014'
figures=repo/'outputs/sim_validation/figures/controller_repair_20261014'
assert not archive.exists(), 'Do not overwrite an existing archive'
entries=[]; skipped=[]
for source in sources:
    group='extended' if 'extended' in source.name else 'pressure'
    for child in sorted(source.iterdir()):
        if child.is_dir():
            if not (child/'result.json').is_file() or not (child/'trajectory.npz').is_file():
                skipped.append(str(child));continue
            files=list(child.rglob('*'))
        else: files=[child]
        for file in files:
            if not file.is_file() or file.suffix.lower() not in ('.json','.npz','.csv','.py','.md','.png'):continue
            rel=file.relative_to(source)
            if file.suffix=='.png': dest=figures/group/rel
            elif len(rel.parts)==1:
                category={'.md':'reports','.py':'frozen_sources','.json':'comparisons'}.get(file.suffix,'other')
                dest=archive/group/category/rel
            else:dest=archive/group/rel
            dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,dest)
            original=hashlib.sha256(file.read_bytes()).hexdigest()
            assert original==hashlib.sha256(dest.read_bytes()).hexdigest()
            entries.append(dict(repository_path=dest.relative_to(repo).as_posix(),original_path=str(file),bytes=file.stat().st_size,sha256=original))
manifest=dict(status='experimental archives; not accepted production policies',source_roots=[str(p) for p in sources],skipped_empty_or_incomplete=skipped,files=entries,notes=['Original metadata retained byte-for-byte; local paths remain historical provenance. Use repository_path for access.','Legacy sources and physical models differ between runs. Compare only compatible protocols and hashes.','Reports are original D-drive documents copied for publication, not rewritten.'])
canonical=sources[1]/'publication_manifest_20261014.json'
canonical.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
shutil.copy2(canonical,archive/'publication_manifest.json')
print('files',len(entries),'MB',round(sum(e['bytes'] for e in entries)/1024**2,2),'runs',sum(1 for e in entries if e['repository_path'].endswith('/trajectory.npz')),'max_file_MB',round(max(e['bytes'] for e in entries)/1024**2,2))
print('manifest',archive/'publication_manifest.json')

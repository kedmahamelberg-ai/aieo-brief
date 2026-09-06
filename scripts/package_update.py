#!/usr/bin/env python3
"""Package the full source, built preview and verified installation manifest."""
import argparse,hashlib,json,shutil,subprocess,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--portable-preview',required=True);p.add_argument('--validation',required=True);a=p.parse_args()
 output=Path(a.output).resolve();portable=Path(a.portable_preview).resolve();report=Path(a.validation).resolve()
 if output==ROOT or ROOT in output.parents or output.exists():raise ValueError('Choose a new package directory outside the source repository.')
 if not (ROOT/'_site/index.html').exists() or not portable.is_file() or not report.is_file():raise ValueError('Build and verify the website and preview before packaging.')
 files=sorted(set(subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0'))-{'','SHA256SUMS.txt'})
 files=[n for n in files if (ROOT/n).is_file()]
 for name in files:
  if (ROOT/name).is_symlink() or 'private' in Path(name).parts or name.startswith(('.env','.git/','node_modules/','_site/')):raise ValueError('Unexpected private/build input in source package: '+name)
 (ROOT/'SHA256SUMS.txt').write_text(''.join(sha(ROOT/name)+'  '+name+'\n' for name in files))
 files=sorted(files+['SHA256SUMS.txt']);source=output/'Repository';source.mkdir(parents=True)
 for name in files:
  target=source/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,target)
 shutil.copytree(ROOT/'_site',output/'Preview')
 shutil.copy2(portable,output/portable.name)
 shutil.copy2(ROOT/'OWNER-SETUP.md',output/'OWNER-SETUP.md')
 shutil.copytree(ROOT/'owner-tools',output/'owner-tools')
 for name in ('START-HERE.html','INSTALL-BRIEF.command'):shutil.copy2(ROOT/'distribution'/name,output/name)
 (output/'INSTALL-BRIEF.command').chmod(0o755)
 shutil.copy2(report,output/'VALIDATION-RESULTS.json')
 (output/'FILES-TO-INSTALL.tsv').write_text(''.join(sha(source/name)+'\t'+name+'\n' for name in files))
 archive=output.with_suffix('.zip')
 with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for path in sorted(output.rglob('*')):
   if path.is_file():z.write(path,Path(output.name)/path.relative_to(output))
 print(json.dumps({'repository_files':len(files),'archive':str(archive),'bytes':archive.stat().st_size,'sha256':sha(archive)},indent=2))
if __name__=='__main__':main()

"""Explicit compiler/decompiler routes; converted text is never called original source."""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile

REPO_ROOT = Path(__file__).resolve().parents[3]
ROOT = REPO_ROOT.parent


def ruri_backend():
    """Find Ruri in any source checkout and use an explicitly configured runtime first."""
    ruri = Path(os.environ.get('RENDERDOC_MCP_RURI_DLL') or
                REPO_ROOT / 'tools/ruri_shader_decompiler/Ruri.ShaderDecompiler.dll')
    candidates = []
    if os.environ.get('DOTNET_ROOT'):
        candidates.append(Path(os.environ['DOTNET_ROOT']) / ('dotnet.exe' if os.name == 'nt' else 'dotnet'))
    candidates.append(ROOT / 'dotnet' / ('dotnet.exe' if os.name == 'nt' else 'dotnet'))
    system = shutil.which('dotnet')
    if system:
        candidates.append(Path(system))
    dotnet = next((p for p in candidates if p.is_file()), None)
    return ruri, dotnet


def executables():
    sdk = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Windows Kits/10/bin'
    def find(name):
        override = os.environ.get('RENDERDOC_MCP_' + name.upper().replace('-', '_'))
        if override and Path(override).is_file():
            return override
        bundled = ROOT / 'implementation/shader-conversion/dxc/bin/x64/dxc.exe'
        if name == 'dxc' and bundled.is_file():
            return str(bundled)
        found = shutil.which(name)
        if found:
            return found
        if name in ('dxc', 'fxc'):
            candidates = sorted(sdk.glob('*/x64/' + name + '.exe'), reverse=True)
        else:
            candidates = [ROOT / 'implementation/shader-conversion/build/Release/spirv-cross.exe'] if name == 'spirv-cross' else [ROOT / 'implementation/shader-conversion/glslang-build/StandAlone/Release/glslang.exe']
        return str(next((p for p in candidates if p.is_file()), '')) or None
    return {key: find(key) for key in ('dxc', 'fxc', 'spirv-cross', 'glslang')}


def convert(source_path, source_language, target_language, dest, stage, entry='main', profile=None):
    source, target = source_language.lower(), target_language.lower()
    stages = {'vs': 'vert', 'ps': 'frag', 'cs': 'comp', 'gs': 'geom', 'hs': 'tesc', 'ds': 'tese'}
    if stage not in stages or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', entry):
        raise ValueError('Provide valid stage vs/ps/cs/gs/hs/ds and entry identifier')
    if source not in {'hlsl', 'glsl', 'spirv', 'dxbc', 'dxil'} or target not in {'hlsl', 'glsl', 'msl', 'spirv', 'dxbc', 'dxil'}:
        raise ValueError('Unsupported language/encoding')
    src, dst = Path(source_path).resolve(), Path(dest).resolve()
    if not src.is_file() or dst.exists() or Path(str(dst)+'.conversion.json').exists():
        raise ValueError('Source must exist and destination/sidecar must be new')
    backend = executables()
    commands = []
    dst.parent.mkdir(parents=True, exist_ok=True)
    input_hash = hashlib.sha256(src.read_bytes()).hexdigest()
    def run(key, args):
        executable = backend.get(key)
        if not executable:
            raise RuntimeError('Missing backend: '+key)
        proc = subprocess.run([executable]+list(map(str, args)), capture_output=True, text=True,
                              encoding='utf-8', errors='replace', timeout=60,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        commands.append({'backend': key, 'executable': executable, 'arguments': list(map(str,args)),
                         'exit_code': proc.returncode, 'diagnostics': (proc.stdout+proc.stderr)[-16000:]})
        if proc.returncode:
            raise RuntimeError(key+' failed: '+(proc.stdout+proc.stderr)[-3000:])
    result = {'source': str(src), 'source_language': source, 'target_language': target, 'stage': stage,
              'input_sha256': input_hash, 'entry': entry, 'commands': commands,
              'semantic_equivalence_verified': False,
              'limitations': 'Bindings, coordinate conventions, entry points and precision require target-runtime validation. Decompiled code is reconstructed, not original source.'}
    try:
        with tempfile.TemporaryDirectory(prefix='rd_shader_') as temp:
            work = Path(temp)
            output = work/'output'
            if source in {'dxbc', 'dxil'}:
                ruri, dotnet = ruri_backend()
                backend['ruri'] = str(dotnet) if ruri.is_file() and dotnet else None
                hlsl = work/'reconstructed.hlsl'
                run('ruri', [ruri, src, hlsl, '--shader-model', '50' if source == 'dxbc' else '60'])
                src, source = hlsl, 'hlsl'
                result['decompiled'] = True
            if source == target:
                shutil.copyfile(src, output)
            elif source == 'hlsl' and target in {'dxbc', 'dxil'}:
                expected = stage+('_5_0' if target == 'dxbc' else '_6_0')
                chosen = profile or expected
                if not re.fullmatch(stage+r'_[56]_[0-9]', chosen):
                    raise ValueError('Profile must match stage and shader model 5/6')
                if target == 'dxbc':
                    run('fxc', ['/T', chosen, '/E', entry, '/Fo', output, '/I', Path(source_path).resolve().parent, src])
                else:
                    run('dxc', ['-T', chosen, '-E', entry, '-Fo', output, '-I', Path(source_path).resolve().parent, src])
            else:
                spv = src
                if source == 'hlsl':
                    spv = work/'intermediate.spv'
                    chosen = profile or stage+'_6_0'
                    if not re.fullmatch(stage+r'_6_[0-9]', chosen):
                        raise ValueError('SPIR-V compilation requires matching shader model 6 profile')
                    run('dxc', ['-spirv', '-T', chosen, '-E', entry, '-Fo', spv, '-I', Path(source_path).resolve().parent, src])
                elif source == 'glsl':
                    spv = work/'intermediate.spv'
                    run('glslang', ['-V', '-S', stages[stage], '-e', entry, '-o', spv, src])
                if target == 'spirv':
                    shutil.copyfile(spv, output)
                elif target in {'glsl', 'hlsl', 'msl'}:
                    flags = {'glsl': ['--version', '450'], 'hlsl': ['--hlsl', '--shader-model', '60'], 'msl': ['--msl']}[target]
                    run('spirv-cross', [spv, '--entry', entry, '--stage', stages[stage], '--output', output]+flags)
                else:
                    raise ValueError('This source/target route requires an explicit intermediate HLSL conversion')
            if not output.is_file() or not output.stat().st_size:
                raise RuntimeError('Backend produced no output')
            # Exclusive creation protects an existing output even if another process races us.
            with dst.open('xb') as stream:
                stream.write(output.read_bytes())
        result.update(ok=True, path=str(dst), output_sha256=hashlib.sha256(dst.read_bytes()).hexdigest())
    except Exception as exc:
        result.update(ok=False, error=str(exc))
    Path(str(dst)+'.conversion.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def register_shader_tools(app, live):
    @app.tool()
    def get_shader_conversion_capabilities() -> dict:
        """Inspect installed DXC, FXC, SPIRV-Cross and glslang. Missing backends disable their routes; no automatic downloads."""
        ruri, dotnet = ruri_backend()
        return {'backends': executables(), 'routes': ['HLSL -> DXBC/DXIL/SPIR-V', 'GLSL -> SPIR-V',
            'SPIR-V -> HLSL/GLSL/MSL', 'DXBC/DXIL -> reconstructed HLSL -> supported target'],
            'ruri_available': ruri.is_file() and dotnet is not None,
            'ruri_dll': str(ruri), 'dotnet': str(dotnet) if dotnet else None}

    @app.tool()
    def convert_shader_language(source_path: str, source_language: str, target_language: str, dest: str,
                                stage: str, entry: str = 'main', profile: str | None = None) -> dict:
        """Compile/decompile/cross-compile local shader files with installed backends. No source overwrite. Saves diagnostics/provenance sidecar; success does NOT establish visual/semantic equivalence. Binary DXBC/DXIL conversions reconstruct HLSL first."""
        return convert(source_path, source_language, target_language, dest, stage, entry, profile)

    @app.tool()
    def debug_shader_invocation(eid: int, stage: str, invocation: dict, dest: str, window_id: str,
                                expected_capture: str, max_steps: int = 100000) -> dict:
        """Export full RenderDoc debugger states for ps/vs/cs. PS invocation {x,y,sample?,primitive?,view?}; VS {vertex,index,instance,view?}; CS {group:[x,y,z],thread:[x,y,z]}. Requires updated bridge. No source edits. Incomplete/unsupported traces report failure. max_steps capped at 1M."""
        from .asset_workflows import Bundle
        # Dest is a fresh directory, trace is trace.json within it.
        b = Bundle(live, dest, window_id, expected_capture)
        allowed = {'ps': {'x', 'y', 'sample', 'primitive', 'view'}, 'vs': {'vertex', 'instance', 'index', 'view'}, 'cs': {'group', 'thread'}}
        if stage not in allowed or set(invocation)-allowed[stage]:
            raise ValueError('Invalid stage or invocation selectors')
        result = live.client.call('debug_shader_invocation', dict(invocation, eid=eid, stage=stage,
                                  dest=str(b.path/'trace.json'), max_steps=max_steps), window_id=window_id)
        if not result.get('ok'):
            b.errors.append({'tool': 'debug_shader_invocation', 'error': result.get('err')})
        return b.finish({'kind': 'debug_trace', 'eid': eid, 'stage': stage, 'result': result})

    @app.tool()
    def read_shader_debug_trace(path: str, offset: int = 0, limit: int = 50, variable: str | None = None) -> dict:
        """Read a bounded window of saved debugger states. Optional variable substring filters changed variables. Preserves exact raw bits; Float32 views are not type interpretation."""
        if offset < 0 or not 1 <= limit <= 200:
            raise ValueError('offset>=0 and limit 1..200 required')
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        states = data.get('states', [])
        selected = states[offset:offset+limit]
        if variable:
            selected = [dict(s, changes=[c for c in s.get('changes', []) if any(variable in str(c.get(k, {}).get('name', '')) for k in ('before', 'after'))]) for s in selected]
        return {'stage': data.get('stage'), 'complete': data.get('complete'), 'errors': data.get('errors'),
                'total_steps': len(states), 'offset': offset, 'next_offset': offset+len(selected),
                'has_more': offset+len(selected)<len(states), 'states': selected}

import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import os
from renderdoc_mcp.server.shader_conversion import convert, executables, ruri_backend


class ConversionTests(unittest.TestCase):
    def test_compilers_and_cross_language_routes(self):
        if not all(executables().values()):
            self.skipTest('Optional compiler backends not all installed')
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            hlsl = root/'input.hlsl'
            hlsl.write_text('float4 main(float4 position: SV_Position) : SV_Target { return float4(0.2, 0.3, 0.4, 1); }')
            for target in ('dxbc', 'dxil', 'spirv', 'glsl', 'msl'):
                with self.subTest(target=target):
                    result = convert(str(hlsl), 'hlsl', target, str(root/('out.'+target)), 'ps')
                    self.assertTrue(result['ok'], result)
                    self.assertFalse(result['semantic_equivalence_verified'])
            for target in ('hlsl', 'msl'):
                result = convert(str(root/'out.spirv'), 'spirv', target, str(root/('roundtrip.'+target)), 'ps')
                self.assertTrue(result['ok'], result)
            result = convert(str(root/'out.glsl'), 'glsl', 'spirv', str(root/'roundtrip.spv'), 'ps')
            self.assertTrue(result['ok'], result)
            with self.assertRaises(ValueError):
                convert(str(hlsl), 'hlsl', 'glsl', str(hlsl), 'ps')

    def test_dxbc_decompilation_with_optional_runtime(self):
        ruri, dotnet = ruri_backend()
        if not executables()['fxc'] or not ruri.is_file() or dotnet is None:
            self.skipTest('Optional FXC/Ruri/.NET backends not installed')
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            source = root/'input.hlsl'
            source.write_text('float4 main() : SV_Target { return float4(1, 0, 0, 1); }')
            result = convert(str(source), 'hlsl', 'dxbc', str(root/'out.dxbc'), 'ps')
            self.assertTrue(result['ok'], result)
            result = convert(str(root/'out.dxbc'), 'dxbc', 'hlsl', str(root/'reconstructed.hlsl'), 'ps')
            self.assertTrue(result['ok'], result)

    def test_ruri_discovery_in_arbitrarily_named_checkout(self):
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root)/'renderdoc-mcp-fork'
            dll = repo/'tools/ruri_shader_decompiler/Ruri.ShaderDecompiler.dll'
            dll.parent.mkdir(parents=True)
            dll.touch()
            runtime = Path(root)/'custom-dotnet'
            runtime.mkdir()
            executable = runtime/('dotnet.exe' if os.name == 'nt' else 'dotnet')
            executable.touch()
            with patch('renderdoc_mcp.server.shader_conversion.REPO_ROOT', repo), \
                 patch.dict(os.environ, {'DOTNET_ROOT': str(runtime), 'RENDERDOC_MCP_RURI_DLL': ''}):
                self.assertEqual(ruri_backend(), (dll, executable))

    def test_compiler_failure_preserves_diagnostics_without_publishing_output(self):
        with tempfile.TemporaryDirectory() as root:
            source, dest = Path(root)/'broken.hlsl', Path(root)/'out.dxil'
            source.write_text('invalid shader text')
            result = convert(str(source), 'hlsl', 'dxil', str(dest), 'ps')
            self.assertFalse(result['ok'])
            self.assertFalse(dest.exists())
            self.assertTrue(Path(str(dest)+'.conversion.json').exists())


if __name__ == '__main__':
    unittest.main()

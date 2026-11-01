import json
from pathlib import Path
import tempfile
import unittest
from renderdoc_mcp.server.asset_workflows import IDENTITY, Gltf, resolve_camera, scene_bundle, shader_bundle, Bundle, export_textures


class Bridge:
    def __init__(self):
        self.calls = []
        self.capture = 'capture.rdc'

    def require(self, method, p):
        self.calls.append((method, p))
        if method == 'get_capture_status':
            return {'ok': True, 'data': {'loaded': True, 'path': self.capture}}
        if method == 'export_mesh':
            Path(p['dest']).write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\nvt 0 0\nvt 1 0\nvt 0 1\nf 1/1 2/2 3/3\n')
        if method == 'debug_save_texture':
            return {'ok': False, 'err': {'code': 'unsupported_format'}}
        if method in ('get_shader_code', 'get_shader_disasm'):
            data = {'text': 'first' if p['offset'] == 0 else 'second', 'returned': 1, 'truncated': p['offset'] == 0}
            return {'ok': True, 'data': {'code': data} if method == 'get_shader_code' else data}
        return {'ok': True, 'data': {}}


class AssetTests(unittest.TestCase):
    def test_camera_inverse_and_reject_combined_matrix(self):
        view = IDENTITY.copy()
        view[3], view[7], view[11] = -2, -3, -4
        result = resolve_camera(view, IDENTITY, {'slot': 1}, 'RH Y-up')
        self.assertEqual(result['position'], [2, 3, 4])
        view[15] = 0
        with self.assertRaises(ValueError):
            resolve_camera(view, IDENTITY, {'slot': 1}, 'RH Y-up')
        with self.assertRaises(ValueError):
            resolve_camera(IDENTITY, IDENTITY, {}, 'RH')

    def test_scene_places_instances_column_major_and_reports_missing_camera(self):
        with tempfile.TemporaryDirectory() as root:
            dest = str(Path(root)/'bundle')
            transform = IDENTITY.copy()
            transform[3] = 12
            result = scene_bundle(Bridge(), dest, [{'eid': 4, 'instances': [{'matrix': transform, 'evidence': {'cb': 2}}]}], [], None, IDENTITY, 'w', 'capture.rdc')
            gltf = json.loads((Path(dest)/'scene.gltf').read_text())
            self.assertEqual(gltf['nodes'][0]['matrix'][12], 12)
            self.assertEqual(gltf['accessors'][0]['count'], 3)
            self.assertFalse(json.loads(Path(result['path']).read_text())['reconstruction_complete'])
            with self.assertRaises(FileExistsError):
                Bundle(Bridge(), dest, 'w', 'capture.rdc')

    def test_nested_shader_pages_not_silently_empty(self):
        with tempfile.TemporaryDirectory() as root:
            dest = str(Path(root)/'bundle')
            shader_bundle(Bridge(), dest, 4, ['vs'], [], 'w', 'capture.rdc')
            self.assertEqual((Path(dest)/'vs.code.txt').read_text(), 'first\nsecond')
            self.assertEqual((Path(dest)/'vs.disasm.txt').read_text(), 'first\nsecond')

    def test_texture_failure_and_capture_switch(self):
        with tempfile.TemporaryDirectory() as root:
            live = Bridge()
            bundle = Bundle(live, str(Path(root)/'bundle'), 'w', 'capture.rdc')
            data = export_textures(bundle, [{'eid': 1, 'rid': 'ResourceId::2'}])
            self.assertIsNone(data[0]['file'])
            self.assertFalse(bundle.finish({'textures': data})['ok'])
            live.capture = 'other.rdc'
            with self.assertRaises(RuntimeError):
                bundle.call('inspect_mesh', eid=1)


if __name__ == '__main__':
    unittest.main()

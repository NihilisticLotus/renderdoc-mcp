from types import SimpleNamespace as NS
from unittest.mock import patch
import unittest
from tests.test_shader_source_placeholder import shader_module
from bridge_extension.renderdoc_mcp_bridge.domains.frame_graph import FrameGraphService, action_page


def action(eid, name='same name', children=()):
    return NS(eventId=eid, customName=name, flags='Drawcall', children=children,
              GetName=lambda _: 'draw')


class FrameGraphTests(unittest.TestCase):
    def setUp(self):
        self.actions = [action(1, children=[action(2), action(3)]), action(4)]
        self.flat = {a.eventId:a for a in [self.actions[0], *self.actions[0].children, self.actions[1]]}
        self.session, self.revision, self.selected, self.effective = 'capture-a', 7, 3, 2
        self.uses = [NS(eventId=4, usage='CopyDst'), NS(eventId=2, usage='PS_Resource'),
                     NS(eventId=2, usage='ColorTarget'), NS(eventId=3, usage='FutureUnknownUsage')]
        self.controller = NS(GetUsage=lambda _: self.uses)
        self.ctx = NS(IsCaptureLoaded=lambda: True, GetCaptureSessionID=lambda:self.session,
            EventEditRevision=lambda:self.revision, CurSelectedEvent=lambda:self.selected,
            CurEvent=lambda:self.effective, CurRootActions=lambda:self.actions,
            GetStructuredFile=lambda:None, GetAction=self.flat.get,
            GetResources=lambda:[NS(resourceId='ResourceId::9')], GetResourceName=lambda _:'RT',
            Replay=lambda:NS(BlockInvoke=lambda fn:fn(self.controller)))
        self.service = FrameGraphService(self.ctx)
        self.params = dict(session_id=self.session, revision=self.revision)

    def test_marker_identity_and_incremental_order_do_not_merge_names(self):
        first = self.service.collect(dict(self.params, limit=2))['data']
        self.assertEqual([e['eid'] for e in first['events']], [1,2])
        self.assertEqual(first['events'][1]['parents'], [1])
        self.assertTrue(first['has_more'])
        second = self.service.collect(dict(self.params, after_eid=first['next_after_eid'], limit=2))['data']
        self.assertEqual([e['eid'] for e in second['events']], [3,4])
        self.assertFalse(second['has_more'])
        self.assertEqual(second['events'][0]['parents'], [1])
        self.assertEqual((self.selected,self.effective),(3,2))

    def test_usage_paging_keeps_all_roles_and_unknown_values_as_facts(self):
        result = self.service.collect(dict(self.params, rid='ResourceId::9',limit=1))['data']
        self.assertEqual([u['usage'] for u in result['usages']], ['PS_Resource','ColorTarget'])
        self.assertEqual(result['next_after_eid'],2)
        next_page = self.service.collect(dict(self.params,rid='ResourceId::9',after_eid=2,limit=1))['data']
        self.assertEqual(next_page['usages'][0]['usage'],'FutureUnknownUsage')
        self.assertEqual(next_page['inferences'],[])
        self.assertEqual(next_page['scope'],'captured_actions_and_usage')
        self.assertEqual((next_page['selected_eid'],next_page['effective_eid']),(3,2))

    def test_generated_pass_marker_eid_does_not_skip_or_duplicate_children(self):
        roots=[action(38, children=[action(5),action(11)]),action(20),action(37)]
        result=[]; after=0
        for _ in range(10):
            page,more=action_page(roots,None,after,2)
            result.extend(page)
            if not more:break
            after=page[-1]['eid']
        self.assertEqual([e['eid'] for e in result],[5,11,20,37,38])
        self.assertEqual(result[0]['parents'],[38])
        self.assertEqual([e['capture_order'] for e in result],[0,1,2,3,None])

    def test_stale_identity_invalid_pages_and_unknown_resource_rejected(self):
        for update in [dict(session_id='other'),dict(revision=6),dict(limit=0),dict(limit=257),
                       dict(after_eid=True),dict(rid='ResourceId::999')]:
            with self.assertRaises(ValueError):
                self.service.collect(dict(self.params,**update))

    def test_replay_errors_and_mid_collection_capture_changes_are_not_swallowed(self):
        def fail(_):raise RuntimeError('GPU failure')
        self.controller.GetUsage=fail
        with self.assertRaisesRegex(RuntimeError,'GPU failure'):
            self.service.collect(dict(self.params,rid='ResourceId::9'))
        def changed(_):
            self.revision+=1
            return self.uses
        self.controller.GetUsage=changed
        with self.assertRaisesRegex(RuntimeError,'Capture or selection changed'):
            self.service.collect(dict(self.params,rid='ResourceId::9'))

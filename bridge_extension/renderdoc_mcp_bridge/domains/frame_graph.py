"""Captured action/usage facts, without selecting an event or replaying a draw."""
import heapq
from .base import BridgeService, invoke_replay_checked
from .capture import CaptureStatusService


def action_page(actions, structured, after, limit):
    """Generated pass markers can have EIDs greater than their children.

    Traverse for ancestry/order, but select a bounded page by EID. Never use
    traversal position as an EID cursor or imply marker EIDs are GPU ordering.
    """
    def candidates():
        stack = [(iter(actions), [])]
        order = 0
        while stack:
            iterator, parents = stack[-1]
            action = next(iterator, None)
            if action is None:
                stack.pop()
                continue
            eid = int(action.eventId)
            if eid > after:
                yield eid, action, list(parents), order if not action.children else None
            if action.children:
                stack.append((iter(action.children), parents + [eid]))
            else:
                order += 1
    page = heapq.nsmallest(limit + 1, candidates(), key=lambda item:item[0])
    result = [{'eid': eid, 'name': str(action.customName or action.GetName(structured)),
               'flags': str(action.flags), 'parents': parents, 'capture_order': order,
               'children': len(action.children), 'evidence': 'CurRootActions'}
              for eid, action, parents, order in page[:limit]]
    return result, len(page) > limit


class FrameGraphService(BridgeService):
    @staticmethod
    def response(data=None, error=None):
        return {'ok': error is None, 'mode': 'summary', 'data': data,
                'err': {'code': 'frame_graph_error', 'msg': str(error)} if error is not None else None,
                'meta': {'cap': 'active', 'truncated': bool(data and data['has_more'])}}

    def run(self, params):
        try:
            return CaptureStatusService(self.ctx)._invoke_on_ui_thread(lambda: self.collect(params), 120.0)
        except Exception as exc:
            return self.response(error='{}: {}'.format(type(exc).__name__, exc))

    def collect(self, params):
        if not self.ctx.IsCaptureLoaded():
            return self._no_capture()
        if not all(callable(getattr(self.ctx, name, None)) for name in
                   ('GetCaptureSessionID', 'EventEditRevision', 'CurSelectedEvent')):
            raise RuntimeError('Frontend does not support capture-bound frame facts')
        session, revision = self.ctx.GetCaptureSessionID(), self.ctx.EventEditRevision()
        if params.get('session_id') != session or params.get('revision') != revision:
            raise ValueError('Capture identity/revision mismatch; request fresh context')
        after, limit = params.get('after_eid', 0), params.get('limit', 64)
        if (isinstance(after, bool) or not isinstance(after, int) or after < 0 or
                isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 256):
            raise ValueError('after_eid must be non-negative and limit must be 1..256')
        selected, effective = self.ctx.CurSelectedEvent(), self.ctx.CurEvent()
        rid_text = params.get('rid')
        resources, usages = [], []
        if rid_text:
            matches = [resource for resource in self.ctx.GetResources() if str(resource.resourceId) == rid_text]
            if len(matches) != 1:
                raise ValueError('Resource is not in the current capture')
            resource = matches[0]
            resources.append({'rid': str(resource.resourceId), 'name': str(self.ctx.GetResourceName(resource.resourceId)),
                              'evidence': 'GetResources'})
            page = {}
            def collect_usage(controller):
                native = controller.GetUsage(resource.resourceId)
                eids = heapq.nsmallest(limit + 1, set(int(u.eventId) for u in native if int(u.eventId) > after))
                page['more'] = len(eids) > limit
                page['eids'] = eids[:limit]
                selected_ids = set(page['eids'])
                for usage in native:
                    if int(usage.eventId) in selected_ids:
                        usages.append({'eid': int(usage.eventId), 'rid': rid_text,
                                       'usage': str(usage.usage), 'evidence': 'GetUsage'})
            invoke_replay_checked(self.ctx, collect_usage)
            # Pagination is by event, never split multiple usage roles at one event.
            eids, more = page['eids'], page['more']
            events = []
            for eid in eids:
                action = self.ctx.GetAction(eid)
                events.append({'eid': eid, 'name': str(action.customName or action.GetName(self.ctx.GetStructuredFile())) if action else '',
                               'flags': str(action.flags) if action else '', 'parents': [],
                               'children': len(action.children) if action else 0,
                               'evidence': 'GetUsage', 'action_available': action is not None})
        else:
            events, more = action_page(self.ctx.CurRootActions(), self.ctx.GetStructuredFile(), after, limit)
        if (self.ctx.GetCaptureSessionID() != session or self.ctx.EventEditRevision() != revision or
                self.ctx.CurSelectedEvent() != selected or self.ctx.CurEvent() != effective):
            raise RuntimeError('Capture or selection changed while collecting frame facts')
        return self.response({'schema': 1, 'session_id': session, 'revision': revision,
                              'selected_eid': selected, 'effective_eid': effective,
                              'scope': 'captured_actions_and_usage', 'events': events,
                              'resources': resources, 'usages': usages, 'has_more': more,
                              'next_after_eid': events[-1]['eid'] if more and events else None,
                              'inferences': []})

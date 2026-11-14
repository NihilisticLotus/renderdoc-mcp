"""Workflow discovery is additive; unsupported bridges fail explicitly."""


def register_workflow_tools(app, live):
    @app.tool()
    def get_workflow_capabilities(window_id: str) -> dict:
        """Read actual frontend/capture capabilities before Bread-style workflows. Does not select an event, enable editing or change replay state. Requires updated bridge; availability is not proof a particular edit will succeed. B2-B6 adapters report not_integrated explicitly."""
        if not window_id:
            raise ValueError('Explicit window_id required')
        return live.client.call('get_workflow_capabilities', {}, window_id=window_id)

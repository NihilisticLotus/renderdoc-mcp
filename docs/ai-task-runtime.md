# B4 UI task dispatch foundation

UIDispatchTask is a process-local bridge/UI handoff used by the existing capture and event-edit service. It does not add a replay queue or undo history.

A queued timeout cancels the callback before it can perform late mutations. A running timeout raises UIDispatchTimeout with cancelled=false and a task handle: it does not mean rollback, and callers must not automatically retry edits. The eventual state/result/error remains on that handle. Capture/revision validation still happens inside the existing native UI transaction.

This first B4.1a batch does not yet register those handles with an MCP Host, expose a public task polling tool, persist them or implement the embedded AI UI. No existing tool input schema changes. GUI monitoring and crash recovery follow the staged B4 plan in Dev-RenderDoc.

Tests exercise cancellation before dequeue, running timeout and eventual completion, duplicate invocation, invalid wait values and original error propagation. The bridge still supports the bundled Python 3.6 runtime.

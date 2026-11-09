"""Offline regressions for Gemini streamed function-call args and stateless replay.

These cases emulate Google Interactions API SSE events. No network or DB.
"""
from types import SimpleNamespace as NS

from app.services.ai_db_chat import DatabaseFunctionChat


def event(event_type, **kwargs):
    return NS(event_type=event_type, **kwargs)


class StrictSDK:
    """Fail at create(), as the real SDK does for invalid stateless input."""
    def __init__(self, streams):
        self.streams = list(streams)
        self.calls = []
        self.interactions = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        for step in kwargs['input']:
            if step.get('type') == 'function_call':
                if not isinstance(step.get('arguments'), dict):
                    raise ValueError('FunctionCallStep.arguments must be dict')
        return iter(self.streams.pop(0))


class FakeGemini:
    def __init__(self, client):
        self._client = client
        self.options = NS(model='gemini-3.5-flash-lite', thinking_level='low')
    def _code(self, exc):
        return None


class FakeController:
    def __init__(self):
        self.calls = []
    def declarations(self):
        return [{'type':'function', 'name':'get_admin_overview',
                 'parameters':{'type':'object','properties':{}}}]
    def execute(self, name, args):
        self.calls.append((name,args))
        return {'total':3}


def first_stream(*, start_args=None, fragments=('{}',), stop_args=None,
                 with_final_steps=False):
    fc_start = dict(type='function_call', id='fc-123', name='get_admin_overview')
    if start_args is not None:
        fc_start['arguments'] = start_args
    fc_stop = dict(type='function_call', id='fc-123', name='get_admin_overview')
    if stop_args is not None:
        fc_stop['arguments'] = stop_args
    thought = {'type':'thought','signature':'signed-thought'}
    items = [event('step.start',index=0,step=thought),
             event('step.stop',index=0,step=thought),
             event('step.start',index=1,step=fc_start)]
    for fragment in fragments:
        items.append(event('step.delta',index=1,
                           delta=NS(type='arguments_delta',arguments=fragment)))
    items.append(event('step.stop',index=1,step=fc_stop))
    snapshot = NS(status='requires_action')
    if with_final_steps:
        snapshot.steps = [thought, fc_stop]
    items.append(event('interaction.completed',interaction=snapshot))
    return items


def final_stream():
    return [event('step.start',index=0,step=NS(type='model_output')),
            event('step.delta',index=0,delta=NS(type='text',text='Ada 3 siswa aktif.')),
            event('step.stop',index=0,step=NS(type='model_output', content=[{'type':'text','text':'Ada 3 siswa aktif.'}])),
            event('interaction.completed',interaction=NS(status='completed'))]


def run_tool(stream):
    sdk = StrictSDK([stream, final_stream()])
    controller = FakeController()
    output = list(DatabaseFunctionChat(FakeGemini(sdk), controller).stream([], 'Berapa siswa?', 'Kamu AI'))
    return sdk, controller, output


def test_stream_delta_function_args_become_object_for_sdk_history():
    sdk, ctrl, output = run_tool(first_stream())
    assert [v.kind for v in output] == ['db_read_started','text_chunk','completed']
    assert ctrl.calls == [('get_admin_overview', {})]
    history = sdk.calls[1]['input']
    tool_step = next(v for v in history if v['type'] == 'function_call')
    assert tool_step['arguments'] == {} and isinstance(tool_step['arguments'],dict)
    assert next(v for v in history if v['type'] == 'thought')['signature'] == 'signed-thought'
    assert next(v for v in history if v['type'] == 'function_result')['call_id'] == 'fc-123'
    assert all(c['store'] is False for c in sdk.calls)


def test_fragmented_json_and_empty_snapshot_object_does_not_lost_arguments():
    # Empty dict at step.stop can reflect a partial server snapshot.
    sdk, ctrl, output = run_tool(first_stream(
        start_args={}, fragments=('{"overdue', '_only":true}'), stop_args={}))
    # Controller deliberately accepts the args to isolate transport reconstruction.
    assert ctrl.calls == [('get_admin_overview', {'overdue_only':True})]
    assert sdk.calls[1]['input'][2]['arguments'] == {'overdue_only': True}
    assert output[-1].kind == 'completed'


def test_final_snapshot_json_string_is_normalized():
    sdk, ctrl, output = run_tool(first_stream(
        start_args='{}', fragments=(), stop_args='{}', with_final_steps=True))
    assert sdk.calls[1]['input'][2]['arguments'] == {}
    assert ctrl.calls == [('get_admin_overview', {})]
    assert output[-1].kind == 'completed'


def test_invalid_arguments_stop_before_any_database_access():
    sdk = StrictSDK([first_stream(fragments=('not-json',))])
    ctrl = FakeController()
    output = list(DatabaseFunctionChat(FakeGemini(sdk),ctrl).stream([], 'test', 's'))
    assert ctrl.calls == []
    assert output[-1].kind == 'error'
    assert len(sdk.calls) == 1


def test_sdk_validation_metadata_is_safe_and_useful():
    from pydantic import BaseModel, ValidationError
    from app.services.ai_db_chat import _safe_diagnostic
    class Input(BaseModel):
        arguments: dict
    try:
        Input(arguments='{"secret":"never-show"}')
    except ValidationError as exc:
        info = _safe_diagnostic(exc,stage='meminta-respons-gemini')
        assert 'lokasi-validasi=arguments' in info
        assert 'jenis-validasi=dict_type' in info
        assert 'never-show' not in info
    else:
        assert False, 'Pydantic seharusnya menolak string argumen'

import asyncio
import json
import time
import pytest
from fastapi.testclient import TestClient
from app.domain import Puzzle, PlayerAction, PlayerConfig, parse_action, player_messages
from app.judge import LayaJudge, JudgeError
from app.server import create_app

P = {'title':'短汤','surface':'他要水后却没有喝，为什么？','bottom':'SECRET_BOTTOM：他打嗝，服务员吓好了他。','max_rounds':3}

class FakeJudge:
    def __init__(self, fail_once=False, delay=0):
        self.fail_once, self.delay = fail_once, delay
    def status(self): return {'ready':True,'loading':False,'device':'test','context':1024}
    def load(self): return self.status()
    def evaluate(self,puzzle,action,rounds,progress):
        time.sleep(self.delay)
        if self.fail_once:
            self.fail_once=False
            raise JudgeError('temporary judge failure')
        solved=action.kind=='solution'
        return {'reply':'通关，解答正确' if solved else '是','verdict':{'choice':'yes','probabilities':{'yes':1},'confidence':1},
                'progress':{'stage':'complete' if solved else 'partial','label':'已还原' if solved else '找到线索','probabilities':{},'window_rounds':1,'submitted_solution':solved},
                'solved':solved,'judge_ms':1,'device':'test'}

class FakePlayer:
    def __init__(self, solution_after=1): self.calls=0; self.seen=[]; self.solution_after=solution_after
    async def next(self, config,puzzle,rounds):
        self.calls+=1
        self.seen.append(player_messages(puzzle,rounds))
        return PlayerAction(kind='solution' if len(rounds)>=self.solution_after else 'question',text='他在打嗝吗？'),{}
    async def test(self,config): return None

def setup(tmp_path, judge=None, player=None):
    app=create_app(judge or FakeJudge(),player or FakePlayer(),tmp_path / 'runs')
    return app,TestClient(app)

def configure(c):
    r=c.post('/api/config',json={'base_url':'http://127.0.0.1:9999/v1','model':'test-player','api_key':'KEY_DO_NOT_LEAK'})
    assert r.status_code==200
    assert 'KEY_DO_NOT_LEAK' not in r.text

def wait(c,sid):
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        s=c.get('/api/games/'+sid).json()
        if not s['busy']:return s
        time.sleep(.02)
    raise AssertionError('session stuck')

def test_parser_and_endpoint():
    assert parse_action('```json\n{"kind":"solution","text":"完成"}\n```').kind=='solution'
    for text in ['他在打嗝吗？', 'yes', '{}', '他在打嗝吗？\n服务员是在帮助他吗？']:
        action=parse_action(text)
        assert action.kind=='question' and action.text==text
    for bad in ['', ' \n\t ']:
        with pytest.raises(ValueError):parse_action(bad)
    for url in ['https://a.test','https://a.test/v1','https://a.test/v1/chat/completions']:
        assert PlayerConfig(base_url=url).endpoint()=='https://a.test/v1/chat/completions'

def test_secret_allowlist():
    puzzle=Puzzle(**P)
    message=json.dumps(player_messages(puzzle,[{'action':{'kind':'question','text':'水是冷的吗？'},'reply':'无关','secret':'SECRET_EVIDENCE'}]))
    assert all(s not in message for s in ['SECRET_BOTTOM','SECRET_FACT','SECRET_EVIDENCE'])

def test_step_pause_resume_export(tmp_path):
    player=FakePlayer()
    app,c=setup(tmp_path,player=player)
    with c:
        configure(c)
        sid=c.post('/api/games',json={'puzzle':P,'run':False}).json()['id']
        assert c.post(f'/api/games/{sid}/control',json={'action':'step'}).status_code==200
        s=wait(c,sid)
        assert s['status']=='paused' and len(s['rounds'])==1
        c.post(f'/api/games/{sid}/control',json={'action':'resume'})
        s=wait(c,sid)
        assert s['status']=='won' and len(s['rounds'])==2
        export=c.get(f'/api/games/{sid}/export')
        assert 'KEY_DO_NOT_LEAK' not in export.text
        assert all('KEY_DO_NOT_LEAK' not in f.read_text() for f in tmp_path.rglob('*.json'))
        assert c.post(f'/api/games/{sid}/control',json={'action':'step'}).status_code==409
        assert c.get('/api/games').json()[0]['rounds']==2
        assert all('SECRET_BOTTOM' not in json.dumps(m) for m in player.seen)
    # Saved sessions restore after a process restart.
    _,again=setup(tmp_path)
    with again:
        assert again.get(f'/api/games/{sid}').json()['status']=='won'

def test_failed_judge_reuses_player_action(tmp_path):
    player=FakePlayer()
    _,c=setup(tmp_path,FakeJudge(fail_once=True),player)
    with c:
        configure(c)
        sid=c.post('/api/games',json={'puzzle':P,'run':False}).json()['id']
        c.post(f'/api/games/{sid}/control',json={'action':'step'})
        s=wait(c,sid)
        assert s['status']=='error' and s['pending'] and not s['rounds']
        c.post(f'/api/games/{sid}/control',json={'action':'step'})
        s=wait(c,sid)
        assert s['status']=='paused' and len(s['rounds'])==1 and player.calls==1

def test_pause_after_inflight_and_duplicate_control(tmp_path):
    _,c=setup(tmp_path,FakeJudge(delay=.2),FakePlayer(solution_after=100))
    with c:
        configure(c)
        sid=c.post('/api/games',json={'puzzle':P,'run':True}).json()['id']
        assert c.post(f'/api/games/{sid}/control',json={'action':'step'}).status_code==409
        c.post(f'/api/games/{sid}/control',json={'action':'pause'})
        s=wait(c,sid)
        assert len(s['rounds'])==1 and s['status']=='paused'
        assert c.post('/api/config',json={'model':'new','base_url':'http://localhost/v1'}).status_code==200

def test_limit_validation_and_origin(tmp_path):
    _,c=setup(tmp_path,player=FakePlayer(solution_after=100))
    with c:
        assert c.post('/api/config',headers={'origin':'https://evil.example'},json={'model':'x'}).status_code==403
        assert c.post('/api/games',json={'puzzle':{**P,'max_rounds':0}}).status_code==422
        configure(c)
        sid=c.post('/api/games',json={'puzzle':{**P,'max_rounds':1},'run':True}).json()['id']
        assert wait(c,sid)['status']=='exhausted'

def test_only_surface_and_bottom_are_required(tmp_path):
    _,c=setup(tmp_path)
    with c:
        r=c.post('/api/games',json={'puzzle':{'surface':'一个问题','bottom':'一个完整的故事'},'run':False})
        assert r.status_code==200
        assert 'facts' not in r.json()['puzzle']
        assert r.json()['progress']['stage']=='unresolved'

def test_solution_requires_both_judgments():
    # Real aggregation with model outputs isolated; a previous stage cannot force a win.
    j=LayaJudge();j.ready=True;j.device='test';j.fits=lambda *args:True
    predictions=iter([{'choice':'correct','probabilities':{}},{'choice':'partial','probabilities':{}}])
    j.predict=lambda *args:next(predictions)
    r=j.evaluate(Puzzle(**P),PlayerAction(kind='solution',text='他是一个人。'),[],{'stage':'complete'})
    assert not r['solved'] and r['progress']['stage']=='partial'


@pytest.mark.parametrize('verdict,stage,solved', [('yes','complete',True), ('yes','partial',False), ('no','complete',False), ('irrelevant','complete',False)])
def test_plain_question_can_win_only_when_both_judgments_pass(monkeypatch,verdict,stage,solved):
    j=LayaJudge();j.ready=True;j.device='test';j.tok=None
    j.cfg={'head_max_len':64,'max_len':1024}
    monkeypatch.setattr(j,'fits',lambda *args:True)
    predictions=iter([{'choice':verdict,'probabilities':{}},{'choice':stage,'probabilities':{}}])
    j.predict=lambda *args:next(predictions)
    result=j.evaluate(Puzzle(**P),parse_action('他因打嗝要水，服务员把他吓好了，所以不用喝水了吗？'),[],{})
    assert result['solved'] is solved
    assert result['reply'] in {'是','不是','无关'}


def test_public_settings_survive_restart_without_key(tmp_path):
    _,c=setup(tmp_path)
    with c:
        configure(c)
    settings=json.loads((tmp_path/'player-settings.json').read_text())
    assert settings=={'base_url':'http://127.0.0.1:9999/v1','model':'test-player'}
    _,again=setup(tmp_path)
    with again:
        restored=again.get('/api/status').json()['player']
        assert restored['base_url']==settings['base_url'] and restored['model']==settings['model']
        assert not restored['has_key']


def test_leaving_finished_game_clears_current_without_losing_replay(tmp_path):
    _,c=setup(tmp_path,player=FakePlayer(solution_after=0))
    with c:
        configure(c)
        sid=c.post('/api/games',json={'puzzle':P,'run':True}).json()['id']
        assert wait(c,sid)['status']=='won'
        assert c.post(f'/api/games/{sid}/control',json={'action':'leave'}).status_code==200
        assert c.get('/api/status').json()['current'] is None
        assert c.get(f'/api/games/{sid}').json()['status']=='won'

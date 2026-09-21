import asyncio
import json
import httpx
import pytest
from app.domain import PlayerConfig, Puzzle
from app.player import APIPlayer, PlayerError, extract_completion, request_payload

ACTION = '他在打嗝吗？'


def completion(content=ACTION, finish='stop', **message):
    return {'choices':[{'message':{'content':content,**message},'finish_reason':finish}],
            'usage':{'prompt_tokens':20,'completion_tokens':30,'total_tokens':50}}


def test_deepseek_800_tokens_reproduction_and_fix():
    observed=[]
    def upstream(request):
        data=json.loads(request.content);observed.append(data)
        # Reproduce DeepSeek consuming the output budget on reasoning alone.
        if data.get('max_tokens')==800:
            return httpx.Response(200,json=completion(None,'length',reasoning_content='PRIVATE_REASONING'))
        assert set(data)=={'model','messages','stream'}
        return httpx.Response(200,json=completion())
    player=APIPlayer(httpx.MockTransport(upstream))
    config=PlayerConfig(base_url='https://api.deepseek.com',model='deepseek-flash',api_key='KEY_SENTINEL')
    result,usage=asyncio.run(player.next(config,Puzzle(surface='他要水却没有喝。',bottom='SECRET_BOTTOM'),[]))
    assert result.text=='他在打嗝吗？' and usage['total_tokens']==50
    assert len(observed)==1
    assert 'SECRET_BOTTOM' not in json.dumps(observed,ensure_ascii=False)
    assert 'KEY_SENTINEL' not in json.dumps(observed)


def test_ordinary_chat_request_for_every_provider_ignores_obsolete_settings():
    for url in ['https://api.deepseek.com','https://other.example/v1']:
        c=PlayerConfig(base_url=url,model='example',thinking_mode='disabled',max_tokens=800)
        assert request_payload(c,[])=={'model':'example','messages':[],'stream':False}


def test_reasoning_is_not_mistaken_for_the_final_answer():
    for finish in ['length','stop']:
        with pytest.raises(PlayerError) as exc:
            extract_completion(completion(None,finish,reasoning_content=ACTION+'PRIVATE_REASONING'))
        assert '回答' in str(exc.value) and 'PRIVATE_REASONING' not in str(exc.value)
        assert ACTION not in str(exc.value)
    # A real text answer is usable even if the provider reports its own length limit.
    assert extract_completion(completion(ACTION,'length',reasoning_content='PRIVATE_REASONING'))[0]==ACTION


def test_content_blocks_nullable_usage_and_reasoning_exclusion():
    blocks=[{'type':'reasoning','text':'PRIVATE_REASONING'},
            {'type':'text','text':'他在'},
            {'type':'output_text','text':{'value':'打嗝吗？'}}]
    data=completion(blocks,reasoning_content='PRIVATE_REASONING');data['usage']=None
    text,usage=extract_completion(data)
    assert text==ACTION and usage=={}


@pytest.mark.parametrize('data,word',[
    ({},'choices'),
    ({'choices':[]},'choices'),
    ({'choices':[None]},'choices'),
    ({'choices':[{'message':None}]},'message'),
    (completion(None),'空'),
    (completion(None,tool_calls=[{'function':{'arguments':'SECRET'}}]),'工具调用'),
    (completion(None,'content_filter',refusal='SECRET'),'过滤'),
    ({'error':{'message':'SECRET'}},'错误')])
def test_errors_are_specific_and_do_not_echo_provider_data(data,word):
    with pytest.raises(PlayerError) as exc:extract_completion(data)
    assert word in str(exc.value) and 'SECRET' not in str(exc.value)


def test_api_test_uses_same_deepseek_configuration():
    calls=[]
    def upstream(request):
        data=json.loads(request.content);calls.append(data)
        return httpx.Response(200,json=completion())
    asyncio.run(APIPlayer(httpx.MockTransport(upstream)).test(PlayerConfig(base_url='https://api.deepseek.com',model='deepseek-flash')))
    assert set(calls[0])=={'model','messages','stream'}
    assert '只问一个' in calls[0]['messages'][0]['content']
    assert 'JSON' not in json.dumps(calls)


def test_chat_history_contains_plain_questions_and_game_rules():
    from app.domain import player_messages
    messages=player_messages(Puzzle(surface='一个汤面',bottom='SECRET_BOTTOM'),[
        {'action':{'kind':'question','text':ACTION},'reply':'是'}])
    assert messages[2]=={'role':'assistant','content':ACTION}
    assert '每次只问一个问题' in messages[0]['content']
    assert all('JSON' not in m['content'] and 'SECRET_BOTTOM' not in m['content'] for m in messages)

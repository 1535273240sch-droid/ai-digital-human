###############################################################################
#  服务器路由 — 统一异常处理的 API 路由
###############################################################################

import json
import asyncio
from aiohttp import web

from utils.logger import logger


# ─── 路由工具函数 ──────────────────────────────────────────────────────────

def json_ok(data=None):
    """返回成功 JSON 响应"""
    body = {"code": 0, "msg": "ok"}
    if data is not None:
        body["data"] = data
    return web.Response(
        content_type="application/json",
        text=json.dumps(body),
    )


def json_error(msg: str, code: int = -1):
    """返回错误 JSON 响应"""
    return web.Response(
        content_type="application/json",
        text=json.dumps({"code": code, "msg": str(msg)}),
    )


from server.session_manager import session_manager
from server.avatar_routes import setup_avatar_routes

def get_session(request, sessionid: str):
    """从 app 中获取 session 实例"""
    return session_manager.get_session(sessionid)


# ─── 路由处理函数 ──────────────────────────────────────────────────────────

async def human(request):
    """文本输入（echo/chat 模式），支持 voice/emotion 参数"""
    try:
        params: dict = await request.json()

        sessionid: str = params.get('sessionid', '')
        avatar_session = get_session(request, sessionid)
        if avatar_session is None:
            return json_error("session not found")

        if params.get('interrupt'):
            avatar_session.flush_talk()

        datainfo = {}
        if params.get('tts'):  # tts 参数透传（voice, emotion 等）
            datainfo['tts'] = params.get('tts')

        if params['type'] == 'echo':
            avatar_session.put_msg_txt(params['text'], datainfo)
        elif params['type'] == 'chat':
            llm_response = request.app.get("llm_response")
            if llm_response:
                asyncio.get_event_loop().run_in_executor(
                    None, llm_response, params['text'], avatar_session, datainfo
                )

        return json_ok()
    except Exception as e:
        logger.exception('human route exception:')
        return json_error(str(e))


async def interrupt_talk(request):
    """打断当前说话"""
    try:
        params = await request.json()
        sessionid = params.get('sessionid', '')
        avatar_session = get_session(request, sessionid)
        if avatar_session is None:
            return json_error("session not found")
        avatar_session.flush_talk()
        return json_ok()
    except Exception as e:
        logger.exception('interrupt_talk exception:')
        return json_error(str(e))


async def humanaudio(request):
    """上传音频文件"""
    try:
        form = await request.post()
        sessionid = str(form.get('sessionid', ''))
        fileobj = form["file"]
        filebytes = fileobj.file.read()

        datainfo = {}

        avatar_session = get_session(request, sessionid)
        if avatar_session is None:
            return json_error("session not found")
        avatar_session.put_audio_file(filebytes, datainfo)
        return json_ok()
    except Exception as e:
        logger.exception('humanaudio exception:')
        return json_error(str(e))


async def set_audiotype(request):
    """设置自定义状态（动作编排）"""
    try:
        params = await request.json()
        sessionid = params.get('sessionid', '')
        avatar_session = get_session(request, sessionid)
        if avatar_session is None:
            return json_error("session not found")
        avatar_session.set_custom_state(params['audiotype'])
        return json_ok()
    except Exception as e:
        logger.exception('set_audiotype exception:')
        return json_error(str(e))


async def record(request):
    """录制控制"""
    try:
        params = await request.json()
        sessionid = params.get('sessionid', '')
        avatar_session = get_session(request, sessionid)
        if avatar_session is None:
            return json_error("session not found")
        if params['type'] == 'start_record':
            avatar_session.start_recording()
        elif params['type'] == 'end_record':
            avatar_session.stop_recording()
        return json_ok()
    except Exception as e:
        logger.exception('record exception:')
        return json_error(str(e))


async def config_get(request):
    """读取系统配置（密钥打码返回）"""
    from server import appconfig
    return json_ok(data=appconfig.mask(appconfig.load()))


async def config_set(request):
    """保存系统配置（界面里填 API Key 等）"""
    try:
        patch = await request.json()
    except Exception:
        return json_error("请求体不是合法 JSON")
    try:
        from server import appconfig
        return json_ok(data=appconfig.save(patch))
    except Exception as e:
        logger.exception("config_set failed:")
        return json_error(str(e))


async def realtime_ping(request):
    """实时语音可用性检查（前端用来决定是否显示实时模式）"""
    from server import realtime_bridge
    if realtime_bridge.available():
        return json_ok(data={"available": True, "reason": ""})

    from server import appconfig
    if not appconfig.api_key_ok() and not os.getenv("STEPFUN_API_KEY"):
        reason = "未配置 API Key"
    elif not realtime_bridge._HAS_WS:
        reason = "缺少 websocket-client"
    elif not realtime_bridge._HAS_RESAMPLE:
        reason = "缺少 resampy"
    else:
        reason = "未知"
    return json_ok(data={"available": False, "reason": reason})


async def realtime_ws(request):
    """实时语音 WebSocket —— 浏览器麦克风直连，边说边识别。

    协议（客户端 → 服务端）：
        {"sessionid": "..."}      首帧，绑定数字人会话
        二进制帧                  16kHz 单声道 PCM16
        {"type":"cancel"}         打断她
        {"type":"close"}          结束

    服务端 → 客户端：
        {"type":"ready"}          会话就绪
        {"type":"state","state":...}   listening / thinking / ready
        {"type":"text","who":...,"text":...}   识别文本 / 她的回复
        {"type":"error","msg":...}
    """
    sessionid = request.query.get("sessionid", "")
    avatar_session = get_session(request, sessionid)
    if avatar_session is None:
        return json_error("session not found")

    from server import realtime_bridge
    if not realtime_bridge.available():
        return json_error("实时语音不可用（检查 STEPFUN_API_KEY 与 websocket-client）")

    from server import persona

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    loop = asyncio.get_event_loop()

    def push(payload):
        """把消息推给浏览器（跨线程）。"""
        try:
            asyncio.run_coroutine_threadsafe(
                ws.send_str(json.dumps(payload, ensure_ascii=False)), loop)
        except Exception:
            pass

    rt = realtime_bridge.RealtimeSession(
        avatar_session,
        on_text=lambda who, text: push({"type": "text", "who": who, "text": text}),
        on_state=lambda st: push({"type": "state", "state": st}),
        voice=persona.get_voice(),
        instructions=persona.apply_name(
            persona.get_persona(), persona.get_name()),
    )

    try:
        await loop.run_in_executor(None, rt.start)
        await ws.send_str(json.dumps({"type": "ready"}, ensure_ascii=False))
        logger.info("[Realtime] 会话建立 sessionid=%s", sessionid)

        async for msg in ws:
            if msg.type == web.WSMsgType.BINARY:
                # 浏览器推来的 16k PCM16，原样转发
                rt.send_audio(msg.data)
            elif msg.type == web.WSMsgType.TEXT:
                try:
                    d = json.loads(msg.data)
                except json.JSONDecodeError:
                    continue
                t = d.get("type")
                if t == "cancel":
                    rt.cancel()
                elif t == "close":
                    break
            elif msg.type in (web.WSMsgType.ERROR, web.WSMsgType.CLOSE):
                break

    except Exception as e:
        logger.exception("[Realtime] 会话异常")
        try:
            await ws.send_str(json.dumps(
                {"type": "error", "msg": str(e)}, ensure_ascii=False))
        except Exception:
            pass
    finally:
        rt.close()
        logger.info("[Realtime] 会话结束 sessionid=%s", sessionid)

    return ws


async def persona_get(request):
    """读取人设与音色配置（供 realtime.html 的设置面板使用）"""
    from server import persona
    return json_ok(data=persona.load())


async def persona_set(request):
    """更新人设与音色配置"""
    try:
        patch = await request.json()
    except Exception:
        return json_error("请求体不是合法 JSON")
    try:
        from server import persona
        return json_ok(data=persona.save(patch))
    except Exception as e:
        logger.exception("persona_set failed:")
        return json_error(str(e))


async def tts_preview(request):
    """音色试听：合成一句话直接返回音频字节"""
    try:
        params = await request.json()
    except Exception:
        return json_error("请求体不是合法 JSON")

    voice = (params.get("voice") or "").strip()
    text = (params.get("text") or "你好呀，我是小雅。").strip()
    if not voice:
        return json_error("voice is required")

    import os as _os
    import requests as _requests

    base = _os.getenv("STEPFUN_API_BASE", "https://api.stepfun.com/v1").rstrip("/")
    key = _os.getenv("STEPFUN_API_KEY", "")
    if not key:
        return json_error("STEPFUN_API_KEY 未配置")

    try:
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(
            None,
            lambda: _requests.post(
                f"{base}/audio/speech",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": _os.getenv("STEPFUN_TTS_MODEL", "stepaudio-2.5-tts"),
                    "input": text,
                    "voice": voice,
                    "response_format": "mp3",
                },
                timeout=60,
            ),
        )
    except Exception as e:
        logger.exception("tts_preview failed:")
        return json_error(f"合成失败: {e}")

    if res.status_code != 200:
        return json_error(f"云端返回 {res.status_code}: {res.text[:200]}")

    return web.Response(body=res.content, content_type="audio/mpeg")


async def is_speaking(request):
    """查询是否正在说话"""
    params = await request.json()
    sessionid = params.get('sessionid', '')
    avatar_session = get_session(request, sessionid)
    if avatar_session is None:
        return json_error("session not found")
    return json_ok(data=avatar_session.is_speaking())

async def sse_handler(request):
    """SSE 事件流，推送服务器状态更新到客户端"""
    sessionid = request.query.get('sessionid', '')
    avatar_session = session_manager.get_session(sessionid)
    if avatar_session is None:
        return json_error("session not found")

    response = web.StreamResponse(
        status=200,
        reason='OK',
        headers={
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*',
        }
    )
    await response.prepare(request)

    import queue
    msgqueue = queue.Queue()
    avatar_session.add_msgqueue(msgqueue)

    try:
        while True:
            try:
                msg = msgqueue.get_nowait()
                await response.write(f"data: {msg}\n\n".encode('utf-8'))
            except queue.Empty:
                await asyncio.sleep(0.01)
    except (asyncio.CancelledError, ConnectionResetError):
        logger.info('SSE connection closed for session: %s', sessionid)
    finally:
        if msgqueue in avatar_session.msgqueues:
            avatar_session.msgqueues.remove(msgqueue)

    return response


async def admin_config(request):
    """Admin: 获取全局配置参数"""
    try:
        opt = request.app.get("opt")
        if opt:
            return json_ok(data={"config": vars(opt)})
        return json_error("Config not found")
    except Exception as e:
        logger.exception('admin_config exception:')
        return json_error(str(e))


async def admin_sessions(request):
    """Admin: 获取活跃的会话及其配置"""
    try:
        sessions_info = []
        for sid, avatar_session in session_manager.sessions.items():
            if avatar_session:
                s_opt = getattr(avatar_session, 'opt', None)
                s_data = {
                    "sessionid": sid,
                    "speaking": avatar_session.is_speaking() if hasattr(avatar_session, 'is_speaking') else False,
                    "recording": getattr(avatar_session, 'recording', False),
                }
                if s_opt:
                    s_data.update({
                        "model": getattr(s_opt, "model", ""),
                        "avatar_id": getattr(s_opt, "avatar_id", ""),
                        "REF_FILE": getattr(s_opt, "REF_FILE", ""),
                        "transport": getattr(s_opt, "transport", ""),
                        "batch_size": getattr(s_opt, "batch_size", 0),
                        "customopt": getattr(s_opt, "customopt", []),
                    })
                sessions_info.append(s_data)
        return json_ok(data={"sessions": sessions_info})
    except Exception as e:
        logger.exception('admin_sessions exception:')
        return json_error(str(e))


# ─── 路由注册 ──────────────────────────────────────────────────────────────

async def index(request):
    """默认首页：数字人主界面（realtime.html）"""
    opt = request.app.get("opt")
    if opt and opt.transport == 'rtmp':
        raise web.HTTPFound('/rtmpapi.html')
    if opt and opt.transport == 'rtcpush':
        raise web.HTTPFound('/rtcpushapi.html')
    # webrtc / virtualcam 走语音球界面
    raise web.HTTPFound('/realtime.html')


def setup_routes(app):
    """注册所有路由到 aiohttp app"""
    app.router.add_get("/", index)
    app.router.add_post("/human", human)
    app.router.add_post("/humanaudio", humanaudio)
    app.router.add_post("/set_audiotype", set_audiotype)
    app.router.add_post("/record", record)
    app.router.add_post("/interrupt_talk", interrupt_talk)
    app.router.add_post("/is_speaking", is_speaking)
    app.router.add_get("/api/admin/config", admin_config)
    app.router.add_get("/api/admin/sessions", admin_sessions)
    app.router.add_get('/sse', sse_handler)

    # ── 人设 / 音色配置（realtime.html 设置面板） ──
    app.router.add_get("/api/persona", persona_get)
    app.router.add_post("/api/persona", persona_set)
    app.router.add_post("/api/tts_preview", tts_preview)

    # ── 实时语音（ping 必须注册在 ws 之前，否则会被 ws 处理器吞掉）──
    app.router.add_get("/api/realtime/ping", realtime_ping)
    app.router.add_get("/api/realtime", realtime_ws)

    # ── 系统配置（界面里填 API Key） ──
    app.router.add_get("/api/config", config_get)
    app.router.add_post("/api/config", config_set)

    # ── ASR endpoint: cloud (StepFun) or local SenseVoice/FunASR ── Issue #604 ──
    try:
        from server.asr_server import (
            asr_websocket_handler,
            is_funasr_available,
            use_cloud_asr,
        )
        if use_cloud_asr():
            app.router.add_get("/api/asr", asr_websocket_handler)
            logger.info("[ASR] Cloud (StepFun) ASR endpoint enabled at /api/asr")
        elif is_funasr_available():
            app.router.add_get("/api/asr", asr_websocket_handler)
            logger.info("[ASR] Local SenseVoice ASR endpoint enabled at /api/asr")
        else:
            logger.info("[ASR] No ASR backend — set STEPFUN_API_KEY for cloud ASR, "
                        "or pip install funasr modelscope for local ASR")
    except Exception as e:
        logger.warning(f"[ASR] Failed to register ASR endpoint: {e}")

    # 注册 avatar 生成相关的路由
    setup_avatar_routes(app)

    app.router.add_static('/', path='web')

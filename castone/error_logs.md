puco_backend   | INFO:     172.18.0.6:53370 - "POST /api/puco/rooms/ HTTP/1.1" 200 OK
puco_backend   | INFO:     ('172.18.0.6', 53374) - "WebSocket /api/puco/ws/lobby/47ebfb95-c84e-4d5d-9d8f-ca090b803743" [accepted]
puco_backend   | INFO:     connection open
puco_backend   | INFO:     172.18.0.6:53384 - "GET /api/bot-types HTTP/1.1" 200 OK
puco_backend   | INFO:     172.18.0.6:53390 - "GET /api/bot-types HTTP/1.1" 200 OK
puco_backend   | INFO:     172.18.0.6:53400 - "POST /api/puco/game/47ebfb95-c84e-4d5d-9d8f-ca090b803743/add-bot HTTP/1.1" 200 OK
puco_backend   | INFO:     127.0.0.1:39366 - "GET /health HTTP/1.1" 200 OK
puco_backend   | INFO:     172.18.0.6:39730 - "POST /api/puco/game/47ebfb95-c84e-4d5d-9d8f-ca090b803743/start HTTP/1.1" 400 Bad Request
puco_backend   | INFO:     127.0.0.1:39382 - "GET /health HTTP/1.1" 200 OK
puco_backend   | INFO:     172.18.0.6:39742 - "POST /api/puco/game/47ebfb95-c84e-4d5d-9d8f-ca090b803743/add-bot HTTP/1.1" 200 OK
puco_backend   | [STATE_TRACE] sync_to_redis_start game=47ebfb95-c84e-4d5d-9d8f-ca090b803743 finished=False ttl=900
puco_backend   | [STATE_TRACE] sync_to_redis_end game=47ebfb95-c84e-4d5d-9d8f-ca090b803743
puco_backend   | [STATE_TRACE] ws_broadcast_start game=47ebfb95-c84e-4d5d-9d8f-ca090b803743
puco_backend   | [STATE_TRACE] ws_broadcast_end game=47ebfb95-c84e-4d5d-9d8f-ca090b803743
puco_backend   | [BOT_TRACE] schedule_check game=47ebfb95-c84e-4d5d-9d8f-ca090b803743 next_idx=0 current_player_idx=0 governor_idx=0 agent_selection=player_0 players=['94881c94-e014-45bc-b0a3-132e8be2cf79', 'BOT_ppo', 'BOT_ppo']
puco_backend   | [BOT_TRACE] schedule_human game=47ebfb95-c84e-4d5d-9d8f-ca090b803743 next_actor=94881c94-e014-45bc-b0a3-132e8be2cf79 idx=0
puco_backend   | [WS_TRACE] ws_broadcast_start game_id=47ebfb95-c84e-4d5d-9d8f-ca090b803743 source=direct message_type=STATE_UPDATE
puco_backend   | [WS_TRACE] ws_broadcast_end game_id=47ebfb95-c84e-4d5d-9d8f-ca090b803743 source=manager message_type=STATE_UPDATE connection_count=0
puco_backend   | [WS_TRACE] ws_broadcast_end game_id=47ebfb95-c84e-4d5d-9d8f-ca090b803743 source=direct message_type=STATE_UPDATE connection_count=0
puco_backend   | INFO:     172.18.0.6:35124 - "POST /api/puco/game/47ebfb95-c84e-4d5d-9d8f-ca090b803743/start HTTP/1.1" 200 OK
puco_backend   | INFO:     connection closed
puco_backend   | INFO:     ('172.18.0.6', 35138) - "WebSocket /api/puco/ws/47ebfb95-c84e-4d5d-9d8f-ca090b803743" [accepted]
puco_backend   | [WS_TRACE] ws_connect game=47ebfb95-c84e-4d5d-9d8f-ca090b803743 connection_id=preauth-281472659298624 user_id=None
puco_backend   | INFO:     connection open
puco_backend   | [WS_TRACE] ws_receive game=47ebfb95-c84e-4d5d-9d8f-ca090b803743 connection_id=preauth-281472659298624 user_id=None message_type=auth
puco_backend   | [WS_TRACE] ws_auth_ok_sent game=47ebfb95-c84e-4d5d-9d8f-ca090b803743 connection_id=preauth-281472659298624 user_id=94881c94-e014-45bc-b0a3-132e8be2cf79
puco_backend   | [WS_TRACE] ws_connect game=47ebfb95-c84e-4d5d-9d8f-ca090b803743 connection_id=ws-1 user_id=94881c94-e014-45bc-b0a3-132e8be2cf79
puco_backend   | [WS_TRACE] ws_subscribe game_id=47ebfb95-c84e-4d5d-9d8f-ca090b803743 connection_id=ws-1 user_id=94881c94-e014-45bc-b0a3-132e8be2cf79
puco_backend   | [WS_TRACE] redis_listener_subscribed game_id=47ebfb95-c84e-4d5d-9d8f-ca090b803743
puco_backend   | INFO:     127.0.0.1:54128 - "GET /health HTTP/1.1" 200 OK
puco_backend   | INFO:     172.18.0.6:35152 - "POST /api/puco/game/47ebfb95-c84e-4d5d-9d8f-ca090b803743/action HTTP/1.1" 404 Not Found
puco_backend   | INFO:     127.0.0.1:54132 - "GET /health HTTP/1.1" 200 OK
import { useEffect, useRef } from 'react'
import type { GameState } from '../types/gameState'

const WS_RECONNECT_DELAY_MS = 3000

interface UseGameWebSocketOptions {
  gameId: string | null
  token: string | null
  onStateUpdate: (state: GameState, actionMask: number[]) => void
  onGameEnded: (reason: string) => void
  onPlayerDisconnected: (playerId: string) => void
}

/**
 * WebSocket 기반 게임 상태 수신 훅.
 *
 * - gameId 또는 token이 없으면 연결하지 않음
 * - 연결 직후 첫 메시지로 JWT 인증 토큰 전송
 * - STATE_UPDATE / GAME_ENDED / PLAYER_DISCONNECTED 메시지 처리
 * - 동일 상태 수신 시 콜백 중복 호출 없음
 * - 예기치 않은 연결 끊김 시 3초 후 자동 재연결
 * - 언마운트 또는 gameId 변경 시 이전 소켓 정리
 * - 콜백을 ref로 보관하여 stale closure 방지
 */
export function useGameWebSocket({
  gameId,
  token,
  onStateUpdate,
  onGameEnded,
  onPlayerDisconnected,
}: UseGameWebSocketOptions): void {
  // 콜백 ref — effect 재실행 없이 항상 최신 콜백 참조
  const onStateUpdateRef = useRef(onStateUpdate)
  const onGameEndedRef = useRef(onGameEnded)
  const onPlayerDisconnectedRef = useRef(onPlayerDisconnected)
  onStateUpdateRef.current = onStateUpdate
  onGameEndedRef.current = onGameEnded
  onPlayerDisconnectedRef.current = onPlayerDisconnected

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const intentionalCloseRef = useRef(false)

  // 중복 상태 감지용 (JSON 직렬화로 비교)
  const lastStateKeyRef = useRef<string | null>(null)

  useEffect(() => {
    if (!gameId || !token) return

    function connect() {
      intentionalCloseRef.current = false

      const wsUrl = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/v1/ws/game/${gameId}`
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        ws.send(JSON.stringify({ token }))
      }

      ws.onmessage = (event) => {
        let msg: { type: string; data?: GameState; action_mask?: number[]; reason?: string; player_id?: string }
        try {
          msg = JSON.parse(event.data as string)
        } catch {
          return  // 잘못된 JSON은 조용히 무시
        }

        if (msg.type === 'STATE_UPDATE') {
          const stateKey = JSON.stringify({ data: msg.data, mask: msg.action_mask })
          if (stateKey === lastStateKeyRef.current) return  // 동일 상태 중복 무시
          lastStateKeyRef.current = stateKey
          onStateUpdateRef.current(msg.data!, msg.action_mask ?? [])

        } else if (msg.type === 'GAME_ENDED') {
          onGameEndedRef.current(msg.reason ?? '')

        } else if (msg.type === 'PLAYER_DISCONNECTED') {
          onPlayerDisconnectedRef.current(msg.player_id ?? '')
        }
      }

      ws.onclose = () => {
        if (intentionalCloseRef.current) return  // 의도적 종료는 재연결 안 함

        reconnectTimerRef.current = setTimeout(() => {
          if (!intentionalCloseRef.current) connect()
        }, WS_RECONNECT_DELAY_MS)
      }
    }

    connect()

    return () => {
      intentionalCloseRef.current = true
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
      lastStateKeyRef.current = null
    }
  }, [gameId, token])  // gameId 또는 token 변경 시 재연결
}

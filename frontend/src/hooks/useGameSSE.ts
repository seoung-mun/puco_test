import { useEffect, useLayoutEffect, useRef } from 'react'
import type { GameState } from '../types/gameState'

interface ServerInfo {
  players?: Array<{ name: string; player_id: string | null; is_host: boolean; is_spectator: boolean; is_bot: boolean; connected: boolean }>
  host?: string | null
  lobby_status?: string | null
}

interface UseGameSSEOptions {
  /** 멀티플레이어 세션 키. null이면 연결하지 않음 */
  sessionKey: string | null
  /** 플레이어 이름 */
  playerName: string | null
  /** 백엔드 base URL */
  backend: string
  onStateUpdate: (state: GameState) => void
  onLobbyUpdate: (info: ServerInfo) => void
}

const SSE_RECONNECT_DELAY_MS = 3000

/**
 * SSE(Server-Sent Events) 기반 게임/로비 상태 수신 훅.
 *
 * - sessionKey 또는 playerName이 없으면 연결하지 않음
 * - 연결 즉시 ping 수신 → 연결 확인
 * - state_update → onStateUpdate 콜백
 * - lobby_update → onLobbyUpdate 콜백
 * - 연결 끊김 시 3초 후 자동 재연결
 * - 언마운트 또는 sessionKey 변경 시 이전 연결 정리
 */
export function useGameSSE({
  sessionKey,
  playerName,
  backend,
  onStateUpdate,
  onLobbyUpdate,
}: UseGameSSEOptions): void {
  const onStateUpdateRef = useRef(onStateUpdate)
  const onLobbyUpdateRef = useRef(onLobbyUpdate)
  useLayoutEffect(() => {
    onStateUpdateRef.current = onStateUpdate
    onLobbyUpdateRef.current = onLobbyUpdate
  })

  const esRef = useRef<EventSource | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const intentionalCloseRef = useRef(false)

  useEffect(() => {
    if (!sessionKey || !playerName) return

    function connect() {
      intentionalCloseRef.current = false
      const url = `${backend}/api/events/stream?key=${encodeURIComponent(sessionKey!)}&name=${encodeURIComponent(playerName!)}`
      const es = new EventSource(url)
      esRef.current = es

      es.addEventListener('state_update', (e: MessageEvent) => {
        try {
          const gs = JSON.parse(e.data as string) as GameState
          onStateUpdateRef.current(gs)
        } catch { /* 잘못된 JSON 무시 */ }
      })

      es.addEventListener('lobby_update', (e: MessageEvent) => {
        try {
          const info = JSON.parse(e.data as string) as ServerInfo
          onLobbyUpdateRef.current(info)
        } catch { /* 잘못된 JSON 무시 */ }
      })

      es.onerror = () => {
        es.close()
        esRef.current = null
        if (intentionalCloseRef.current) return
        reconnectTimerRef.current = setTimeout(() => {
          if (!intentionalCloseRef.current) connect()
        }, SSE_RECONNECT_DELAY_MS)
      }
    }

    connect()

    return () => {
      intentionalCloseRef.current = true
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      if (esRef.current) {
        esRef.current.close()
        esRef.current = null
      }
    }
  }, [sessionKey, playerName, backend])
}

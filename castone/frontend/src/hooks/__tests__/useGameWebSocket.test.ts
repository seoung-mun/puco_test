/**
 * TDD — useGameWebSocket hook
 *
 * 검증하는 엣지케이스:
 *  1. gameId 없으면 WebSocket 연결 안 함
 *  2. token 없으면 WebSocket 연결 안 함
 *  3. 연결 직후 첫 메시지로 auth token 전송
 *  4. STATE_UPDATE 수신 → onStateUpdate 콜백 호출
 *  5. state가 동일하면 onStateUpdate 재호출 안 함 (중복 렌더 방지)
 *  6. GAME_ENDED 수신 → onGameEnded 콜백 호출
 *  7. PLAYER_DISCONNECTED 수신 → onPlayerDisconnected 콜백 호출
 *  8. 서버에서 잘못된 JSON 수신 → 조용히 무시 (throw 없음)
 *  9. 언마운트 시 WebSocket close() 호출 (메모리 누수 없음)
 * 10. 연결 끊김(onclose) → 3초 후 자동 재연결
 * 11. gameId 변경 → 이전 연결 종료 후 새 연결
 */

import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useGameWebSocket } from '../useGameWebSocket'
import type { GameState } from '../../types/gameState'

// ─── Mock WebSocket ────────────────────────────────────────────────────────────

class MockWebSocket {
  static instances: MockWebSocket[] = []

  url: string
  readyState = WebSocket.CONNECTING  // 0

  onopen: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onerror: ((e: Event) => void) | null = null
  onclose: (() => void) | null = null

  sentMessages: string[] = []
  closeCalled = false

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  send(data: string) {
    this.sentMessages.push(data)
  }

  close() {
    this.closeCalled = true
    this.readyState = WebSocket.CLOSED
    this.onclose?.()
  }

  // ── 테스트 헬퍼: 서버 이벤트 시뮬레이션 ──────────────────────────────────

  simulateOpen() {
    this.readyState = WebSocket.OPEN
    this.onopen?.()
  }

  simulateMessage(payload: object) {
    this.onmessage?.({ data: JSON.stringify(payload) })
  }

  simulateRawMessage(raw: string) {
    this.onmessage?.({ data: raw })
  }

  simulateClose() {
    this.readyState = WebSocket.CLOSED
    this.onclose?.()
  }

  static latest(): MockWebSocket {
    return this.instances[this.instances.length - 1]
  }

  static reset() {
    this.instances = []
  }
}

// ─── 픽스처 ────────────────────────────────────────────────────────────────────

const MOCK_STATE = {
  meta: { active_player: 'player_0', phase: 'role_selection', round: 1 },
  players: {},
  history: [],
} as unknown as GameState

const MOCK_MASK = [1, 0, 1]

// ─── 테스트 ────────────────────────────────────────────────────────────────────

describe('useGameWebSocket', () => {
  let onStateUpdate: ReturnType<typeof vi.fn>
  let onGameEnded: ReturnType<typeof vi.fn>
  let onPlayerDisconnected: ReturnType<typeof vi.fn>

  beforeEach(() => {
    MockWebSocket.reset()
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.useFakeTimers()

    onStateUpdate = vi.fn<[GameState, number[]], void>()
    onGameEnded = vi.fn<[string], void>()
    onPlayerDisconnected = vi.fn<[string], void>()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  // ── 1. gameId 없으면 연결 안 함 ──────────────────────────────────────────

  it('does not create WebSocket when gameId is null', () => {
    renderHook(() =>
      useGameWebSocket({
        gameId: null,
        token: 'tok',
        onStateUpdate,
        onGameEnded,
        onPlayerDisconnected,
      })
    )

    expect(MockWebSocket.instances).toHaveLength(0)
  })

  // ── 2. token 없으면 연결 안 함 ───────────────────────────────────────────

  it('does not create WebSocket when token is null', () => {
    renderHook(() =>
      useGameWebSocket({
        gameId: 'game-123',
        token: null,
        onStateUpdate,
        onGameEnded,
        onPlayerDisconnected,
      })
    )

    expect(MockWebSocket.instances).toHaveLength(0)
  })

  // ── 3. 연결 직후 auth 메시지 전송 ────────────────────────────────────────

  it('sends auth token as first message after connection opens', () => {
    renderHook(() =>
      useGameWebSocket({
        gameId: 'game-123',
        token: 'my-jwt-token',
        onStateUpdate,
        onGameEnded,
        onPlayerDisconnected,
      })
    )

    const ws = MockWebSocket.latest()
    act(() => ws.simulateOpen())

    expect(ws.sentMessages).toHaveLength(1)
    const msg = JSON.parse(ws.sentMessages[0])
    expect(msg).toEqual({ token: 'my-jwt-token' })
  })

  // ── 4. STATE_UPDATE 수신 → onStateUpdate 호출 ────────────────────────────

  it('calls onStateUpdate when STATE_UPDATE message is received', () => {
    renderHook(() =>
      useGameWebSocket({
        gameId: 'game-123',
        token: 'tok',
        onStateUpdate,
        onGameEnded,
        onPlayerDisconnected,
      })
    )

    const ws = MockWebSocket.latest()
    act(() => {
      ws.simulateOpen()
      ws.simulateMessage({ type: 'STATE_UPDATE', data: MOCK_STATE, action_mask: MOCK_MASK })
    })

    expect(onStateUpdate).toHaveBeenCalledOnce()
    expect(onStateUpdate).toHaveBeenCalledWith(MOCK_STATE, MOCK_MASK)
  })

  // ── 5. 동일 상태 수신 → 중복 호출 없음 ──────────────────────────────────

  it('does not call onStateUpdate again if state is identical', () => {
    renderHook(() =>
      useGameWebSocket({
        gameId: 'game-123',
        token: 'tok',
        onStateUpdate,
        onGameEnded,
        onPlayerDisconnected,
      })
    )

    const ws = MockWebSocket.latest()
    act(() => {
      ws.simulateOpen()
      ws.simulateMessage({ type: 'STATE_UPDATE', data: MOCK_STATE, action_mask: MOCK_MASK })
      ws.simulateMessage({ type: 'STATE_UPDATE', data: MOCK_STATE, action_mask: MOCK_MASK })
    })

    // 동일 state + mask → 2번째는 무시
    expect(onStateUpdate).toHaveBeenCalledOnce()
  })

  // ── 6. GAME_ENDED 수신 → onGameEnded 호출 ────────────────────────────────

  it('calls onGameEnded when GAME_ENDED message is received', () => {
    renderHook(() =>
      useGameWebSocket({
        gameId: 'game-123',
        token: 'tok',
        onStateUpdate,
        onGameEnded,
        onPlayerDisconnected,
      })
    )

    const ws = MockWebSocket.latest()
    act(() => {
      ws.simulateOpen()
      ws.simulateMessage({ type: 'GAME_ENDED', reason: 'player_request' })
    })

    expect(onGameEnded).toHaveBeenCalledOnce()
    expect(onGameEnded).toHaveBeenCalledWith('player_request')
  })

  // ── 7. PLAYER_DISCONNECTED → onPlayerDisconnected 호출 ───────────────────

  it('calls onPlayerDisconnected when PLAYER_DISCONNECTED message is received', () => {
    renderHook(() =>
      useGameWebSocket({
        gameId: 'game-123',
        token: 'tok',
        onStateUpdate,
        onGameEnded,
        onPlayerDisconnected,
      })
    )

    const ws = MockWebSocket.latest()
    act(() => {
      ws.simulateOpen()
      ws.simulateMessage({ type: 'PLAYER_DISCONNECTED', player_id: 'player_1' })
    })

    expect(onPlayerDisconnected).toHaveBeenCalledOnce()
    expect(onPlayerDisconnected).toHaveBeenCalledWith('player_1')
  })

  // ── 8. 잘못된 JSON → 조용히 무시 ─────────────────────────────────────────

  it('silently ignores invalid JSON from server', () => {
    renderHook(() =>
      useGameWebSocket({
        gameId: 'game-123',
        token: 'tok',
        onStateUpdate,
        onGameEnded,
        onPlayerDisconnected,
      })
    )

    const ws = MockWebSocket.latest()
    act(() => {
      ws.simulateOpen()
      // 잘못된 JSON → throw 없어야 함
      expect(() => ws.simulateRawMessage('NOT_JSON{{')).not.toThrow()
    })

    expect(onStateUpdate).not.toHaveBeenCalled()
  })

  // ── 9. 언마운트 → close() 호출 ───────────────────────────────────────────

  it('closes WebSocket on unmount', () => {
    const { unmount } = renderHook(() =>
      useGameWebSocket({
        gameId: 'game-123',
        token: 'tok',
        onStateUpdate,
        onGameEnded,
        onPlayerDisconnected,
      })
    )

    const ws = MockWebSocket.latest()
    act(() => ws.simulateOpen())

    unmount()

    expect(ws.closeCalled).toBe(true)
  })

  // ── 10. 연결 끊김 → 3초 후 자동 재연결 ──────────────────────────────────

  it('reconnects 3 seconds after unexpected disconnect', () => {
    renderHook(() =>
      useGameWebSocket({
        gameId: 'game-123',
        token: 'tok',
        onStateUpdate,
        onGameEnded,
        onPlayerDisconnected,
      })
    )

    const ws1 = MockWebSocket.latest()
    act(() => {
      ws1.simulateOpen()
      ws1.simulateClose()  // 예기치 않은 연결 끊김 (close() 호출 없이)
    })

    expect(MockWebSocket.instances).toHaveLength(1)

    act(() => vi.advanceTimersByTime(3000))

    // 3초 후 새 WebSocket 생성됨
    expect(MockWebSocket.instances).toHaveLength(2)
  })

  // ── 11. gameId 변경 → 이전 연결 종료 후 새 연결 ─────────────────────────

  it('closes old WebSocket and opens new one when gameId changes', () => {
    let gameId = 'game-aaa'
    const { rerender } = renderHook(() =>
      useGameWebSocket({
        gameId,
        token: 'tok',
        onStateUpdate,
        onGameEnded,
        onPlayerDisconnected,
      })
    )

    const ws1 = MockWebSocket.latest()
    act(() => ws1.simulateOpen())

    gameId = 'game-bbb'
    rerender()

    expect(ws1.closeCalled).toBe(true)
    expect(MockWebSocket.instances).toHaveLength(2)
    expect(MockWebSocket.latest().url).toContain('game-bbb')
  })
})

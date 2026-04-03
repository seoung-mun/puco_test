// @vitest-environment node

import { describe, expect, it } from 'vitest'

import config from './vite.config'

describe('vite dev server proxy', () => {
  it('enables websocket proxying for /api', () => {
    const apiProxy = config.server?.proxy?.['/api']

    expect(apiProxy).toBeTruthy()
    expect(typeof apiProxy).toBe('object')
    expect(apiProxy).toMatchObject({
      changeOrigin: true,
      ws: true,
    })
  })
})

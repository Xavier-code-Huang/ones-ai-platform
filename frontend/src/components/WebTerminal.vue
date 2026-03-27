<template>
  <div class="web-terminal-container" v-show="visible">
    <div class="terminal-header">
      <div class="terminal-title">
        <span class="terminal-dot"></span>
        🖥️ 服务器终端
        <span class="terminal-server" v-if="serverInfo">{{ serverInfo }}</span>
      </div>
      <div class="terminal-actions">
        <el-button size="small" text @click="reconnect" :loading="connecting" v-if="!connected && !connecting">
          🔄 重连
        </el-button>
        <el-tag v-if="connected" type="success" size="small" effect="dark" round>已连接</el-tag>
        <el-tag v-else-if="connecting" type="warning" size="small" effect="dark" round>连接中...</el-tag>
        <el-tag v-else type="danger" size="small" effect="dark" round>已断开</el-tag>
        <el-button size="small" text circle @click="$emit('close')">
          <el-icon><Close /></el-icon>
        </el-button>
      </div>
    </div>
    <div ref="terminalRef" class="terminal-body"></div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { Close } from '@element-plus/icons-vue'
import { Terminal } from 'xterm'
import { FitAddon } from 'xterm-addon-fit'
import 'xterm/css/xterm.css'

const props = defineProps({
  taskId: { type: Number, required: true },
  visible: { type: Boolean, default: false },
  serverInfo: { type: String, default: '' },
})

const emit = defineEmits(['close'])

const terminalRef = ref(null)
const connected = ref(false)
const connecting = ref(false)

let term = null
let fitAddon = null
let ws = null
let resizeTimer = null

// ---- 初始化终端 ----
function initTerminal() {
  if (term) return

  term = new Terminal({
    cursorBlink: true,
    fontSize: 13,
    fontFamily: '"Cascadia Code", "JetBrains Mono", "Fira Code", monospace',
    theme: {
      background: '#1a1b26',
      foreground: '#c0caf5',
      cursor: '#c0caf5',
      selectionBackground: '#33467c',
      black: '#15161e',
      red: '#f7768e',
      green: '#9ece6a',
      yellow: '#e0af68',
      blue: '#7aa2f7',
      magenta: '#bb9af7',
      cyan: '#7dcfff',
      white: '#a9b1d6',
    },
    scrollback: 5000,
    convertEol: true,
  })

  fitAddon = new FitAddon()
  term.loadAddon(fitAddon)

  term.open(terminalRef.value)
  fitAddon.fit()

  // 键盘输入 → WebSocket binary
  term.onData((data) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      const encoder = new TextEncoder()
      ws.send(encoder.encode(data))
    }
  })

  // 窗口 resize → 发送控制命令
  const observer = new ResizeObserver(() => {
    if (resizeTimer) clearTimeout(resizeTimer)
    resizeTimer = setTimeout(() => {
      if (fitAddon && term) {
        fitAddon.fit()
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({
            type: 'resize',
            cols: term.cols,
            rows: term.rows,
          }))
        }
      }
    }, 200) // debounce 200ms
  })
  observer.observe(terminalRef.value)
}

// ---- WebSocket 连接 ----
function connect() {
  if (ws && ws.readyState <= WebSocket.OPEN) return
  if (!props.taskId) return

  connecting.value = true
  const token = localStorage.getItem('token') || ''
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${protocol}//${window.location.host}/ws/tasks/${props.taskId}/terminal?token=${token}`

  ws = new WebSocket(wsUrl)
  ws.binaryType = 'arraybuffer'

  ws.onopen = () => {
    connected.value = true
    connecting.value = false
    term.writeln('\x1b[32m✓ 已连接到服务器\x1b[0m')
    term.writeln('\x1b[33m提示: 执行 docker ps 查看运行中的容器\x1b[0m')
    term.writeln('')

    // 发送初始 resize
    if (term && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'resize',
        cols: term.cols,
        rows: term.rows,
      }))
    }
  }

  ws.onmessage = (event) => {
    if (event.data instanceof ArrayBuffer) {
      const decoder = new TextDecoder()
      term.write(decoder.decode(event.data))
    } else if (typeof event.data === 'string') {
      // 文本帧（服务端可能发 JSON 控制消息）
      term.write(event.data)
    }
  }

  ws.onerror = () => {
    connecting.value = false
  }

  ws.onclose = (event) => {
    connected.value = false
    connecting.value = false
    if (term) {
      const reason = event.reason || '连接已关闭'
      term.writeln('')
      term.writeln(`\x1b[31m✗ 终端断开: ${reason} (code: ${event.code})\x1b[0m`)
    }
  }
}

function disconnect() {
  if (ws) {
    ws.close()
    ws = null
  }
}

function reconnect() {
  disconnect()
  if (term) {
    term.clear()
    term.writeln('\x1b[33m正在重新连接...\x1b[0m')
  }
  setTimeout(connect, 300)
}

// ---- 生命周期 ----
watch(() => props.visible, (val) => {
  if (val) {
    nextTick(() => {
      initTerminal()
      connect()
      // 延迟 fit 确保 DOM 渲染完成
      setTimeout(() => { if (fitAddon) fitAddon.fit() }, 100)
    })
  } else {
    disconnect()
  }
})

onMounted(() => {
  if (props.visible) {
    nextTick(() => {
      initTerminal()
      connect()
    })
  }
})

onBeforeUnmount(() => {
  disconnect()
  if (resizeTimer) clearTimeout(resizeTimer)
  if (term) {
    term.dispose()
    term = null
  }
})
</script>

<style scoped>
.web-terminal-container {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border);
  border-radius: var(--radius, 8px);
  overflow: hidden;
  background: #1a1b26;
}

.terminal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: #16161e;
  border-bottom: 1px solid #292e42;
}

.terminal-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.82rem;
  font-weight: 500;
  color: #c0caf5;
}

.terminal-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #9ece6a;
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.terminal-server {
  font-size: 0.72rem;
  color: #565f89;
  font-family: var(--font-mono, monospace);
}

.terminal-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.terminal-body {
  height: 360px;
  padding: 4px;
}

/* xterm.js 样式调整 */
.terminal-body :deep(.xterm) {
  height: 100%;
}

.terminal-body :deep(.xterm-viewport) {
  overflow-y: auto !important;
}

.terminal-body :deep(.xterm-viewport::-webkit-scrollbar) {
  width: 6px;
}

.terminal-body :deep(.xterm-viewport::-webkit-scrollbar-thumb) {
  background: #292e42;
  border-radius: 3px;
}

.terminal-body :deep(.xterm-viewport::-webkit-scrollbar-thumb:hover) {
  background: #3b4261;
}
</style>

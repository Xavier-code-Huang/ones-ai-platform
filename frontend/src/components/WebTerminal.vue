<template>
  <div class="web-terminal-container" v-show="visible">
    <div class="terminal-header">
      <div class="terminal-title">
        <span class="terminal-dot" :class="{ 'connected': isConnected, 'error': connectionError, 'replay': mode === 'replay' }"></span>
        <template v-if="mode === 'replay'">
          📼 历史回放
        </template>
        <template v-else>
          🖥️ 容器终端
        </template>
        <span class="terminal-server" v-if="serverInfo">{{ serverInfo }}</span>
        <span class="terminal-server" style="margin-left:8px;color:var(--accent-light);">#{{ ticketIdStr }}</span>
      </div>
      <div class="terminal-actions">
        <!-- 回放模式控制 -->
        <template v-if="mode === 'replay'">
          <el-tag v-if="replayDone" type="info" size="small" effect="dark" round>回放完成</el-tag>
          <el-tag v-else type="warning" size="small" effect="dark" round>
            <span class="replay-anim">▶</span> 回放中 {{ replayProgress }}
          </el-tag>
        </template>
        <!-- 实时模式控制 -->
        <template v-else>
          <el-button size="small" text @click="reconnect" :loading="connecting" v-if="!connected && !connecting">
            🔄 重连
          </el-button>
          <el-tag v-if="connected" type="success" size="small" effect="dark" round>已连接</el-tag>
          <el-tag v-else-if="connecting" type="warning" size="small" effect="dark" round>连接中...</el-tag>
          <el-tag v-else type="danger" size="small" effect="dark" round>已断开</el-tag>
        </template>
      </div>
    </div>
    <div ref="terminalRef" class="terminal-body"></div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount, nextTick, computed } from 'vue'
import { Terminal } from 'xterm'
import { FitAddon } from 'xterm-addon-fit'
import 'xterm/css/xterm.css'

const props = defineProps({
  ticketDbId: { type: Number, required: true },
  ticketIdStr: { type: String, default: '' },
  visible: { type: Boolean, default: false },
  serverInfo: { type: String, default: '' },
  autoResume: { type: Boolean, default: false },
  // 新增：模式和回放数据
  mode: { type: String, default: 'live' }, // 'live' | 'replay'
  replayLogs: { type: Array, default: () => [] },
})

const emit = defineEmits(['connected', 'disconnected'])

const terminalRef = ref(null)
const connected = ref(false)
const connecting = ref(false)
const connectionError = ref(false)

// 回放状态
const replayDone = ref(false)
const replayCurrentLine = ref(0)
let replayTimer = null

const isConnected = computed(() => {
  if (props.mode === 'replay') return !replayDone.value
  return connected.value
})

const replayProgress = computed(() => {
  if (!props.replayLogs.length) return ''
  return `${replayCurrentLine.value}/${props.replayLogs.length}`
})

let term = null
let fitAddon = null
let ws = null
let resizeTimer = null
let userScrolledUp = false // 智能滚动标记

// ---- 初始化终端 ----
function initTerminal() {
  if (term) return

  term = new Terminal({
    cursorBlink: props.mode !== 'replay',
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
    scrollback: 10000,
    convertEol: true,
    disableStdin: props.mode === 'replay',
  })

  fitAddon = new FitAddon()
  term.loadAddon(fitAddon)

  term.open(terminalRef.value)
  fitAddon.fit()

  // 监听用户滚动：如果用户手动滚上去了，不自动跟随
  const viewport = terminalRef.value?.querySelector('.xterm-viewport')
  if (viewport) {
    viewport.addEventListener('scroll', () => {
      const { scrollTop, scrollHeight, clientHeight } = viewport
      // 距离底部 50px 以内视为"在底部"
      userScrolledUp = (scrollHeight - scrollTop - clientHeight) > 50
    })
  }

  if (props.mode !== 'replay') {
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
      }, 200)
    })
    observer.observe(terminalRef.value)
  } else {
    // 回放模式：resize 适配
    const observer = new ResizeObserver(() => {
      if (fitAddon && term) fitAddon.fit()
    })
    observer.observe(terminalRef.value)
  }
}

// ---- 智能滚动到底部 ----
function scrollToBottomIfNeeded() {
  if (!userScrolledUp && term) {
    term.scrollToBottom()
  }
}

// ---- 回放模式 ----
function startReplay() {
  if (!term || !props.replayLogs.length) return

  replayDone.value = false
  replayCurrentLine.value = 0
  userScrolledUp = false
  term.clear()
  term.writeln('\x1b[36m📼 [系统] 开始回放 AI 分析过程...\x1b[0m')
  term.writeln('')

  let idx = 0
  const lines = props.replayLogs

  function writeNext() {
    // 每帧写入的行数根据总量调整：日志少慢一点，多快一点
    const batchSize = lines.length > 500 ? 5 : lines.length > 200 ? 3 : 1
    const delay = lines.length > 500 ? 10 : lines.length > 200 ? 20 : 35

    for (let b = 0; b < batchSize && idx < lines.length; b++, idx++) {
      const log = lines[idx]
      const content = log.content || log
      // 根据日志类型上色
      if (log.log_type === 'system') {
        term.writeln(`\x1b[33m${content}\x1b[0m`)
      } else if (log.log_type === 'stderr') {
        term.writeln(`\x1b[31m${content}\x1b[0m`)
      } else {
        // stdout: 解析 emoji 前缀上色
        term.writeln(colorize(content))
      }
      replayCurrentLine.value = idx + 1
    }

    scrollToBottomIfNeeded()

    if (idx < lines.length) {
      replayTimer = setTimeout(writeNext, delay)
    } else {
      term.writeln('')
      term.writeln('\x1b[36m📼 [系统] 回放完成\x1b[0m')
      replayDone.value = true
      scrollToBottomIfNeeded()
    }
  }

  writeNext()
}

function stopReplay() {
  if (replayTimer) {
    clearTimeout(replayTimer)
    replayTimer = null
  }
}

// 给不同类型的日志行上色
function colorize(text) {
  if (text.startsWith('💭')) return `\x1b[90m${text}\x1b[0m`      // 思考 → 灰色
  if (text.startsWith('⚡')) return `\x1b[33m${text}\x1b[0m`      // 命令 → 黄色
  if (text.startsWith('📖')) return `\x1b[36m${text}\x1b[0m`      // 读文件 → 青色
  if (text.startsWith('✏️')) return `\x1b[32m${text}\x1b[0m`      // 写文件 → 绿色
  if (text.startsWith('🔍')) return `\x1b[35m${text}\x1b[0m`      // 搜索 → 紫色
  if (text.startsWith('📂')) return `\x1b[36m${text}\x1b[0m`      // 浏览 → 青色
  if (text.startsWith('🔧')) return `\x1b[34m${text}\x1b[0m`      // 工具 → 蓝色
  if (text.startsWith('📝')) return `\x1b[37m${text}\x1b[0m`      // 文本 → 白色
  if (text.startsWith('🏁')) return `\x1b[32;1m${text}\x1b[0m`    // 完成 → 亮绿
  if (text.startsWith('🚀')) return `\x1b[34;1m${text}\x1b[0m`    // 初始化 → 亮蓝
  if (text.startsWith('❌')) return `\x1b[31m${text}\x1b[0m`      // 错误 → 红色
  if (text.startsWith('   ↪')) return `\x1b[90m${text}\x1b[0m`   // 结果 → 灰色
  if (text.startsWith('[PHASE]')) return `\x1b[33;1m${text}\x1b[0m`
  return text
}

// ---- WebSocket 连接 (live 模式) ----
function connect() {
  if (ws && ws.readyState <= WebSocket.OPEN) return
  if (!props.ticketDbId) return

  connecting.value = true
  connectionError.value = false
  const token = localStorage.getItem('token') || ''
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const autoResumeFlag = props.autoResume ? 'true' : 'false'
  const wsUrl = `${protocol}//${window.location.host}/ws/tickets/${props.ticketDbId}/terminal?token=${token}&auto_resume=${autoResumeFlag}`

  ws = new WebSocket(wsUrl)
  ws.binaryType = 'arraybuffer'

  ws.onopen = () => {
    connected.value = true
    connecting.value = false
    connectionError.value = false
    term.writeln('\x1b[32m[系统] 已连接到容器终端...\x1b[0m')

    if (term && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'resize',
        cols: term.cols,
        rows: term.rows,
      }))
    }
    emit('connected')
  }

  ws.onmessage = (event) => {
    if (event.data instanceof ArrayBuffer) {
      const decoder = new TextDecoder()
      term.write(decoder.decode(event.data))
    } else if (typeof event.data === 'string') {
      term.write(event.data)
    }
  }

  ws.onerror = () => {
    connecting.value = false
    connectionError.value = true
  }

  ws.onclose = (event) => {
    connected.value = false
    connecting.value = false
    connectionError.value = true
    if (term) {
      const reason = event.reason || '连接已关闭'
      term.writeln('')
      term.writeln(`\x1b[31m[系统] 终端断开: ${reason} (code: ${event.code})\x1b[0m`)
    }
    emit('disconnected')
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
    term.writeln('\x1b[33m[系统] 正在重新连接...\x1b[0m')
  }
  setTimeout(connect, 300)
}

// 暴露方法给父组件
defineExpose({ reconnect, disconnect, startReplay, stopReplay })

// ---- 生命周期 ----
watch(() => props.visible, (val) => {
  if (val) {
    nextTick(() => {
      initTerminal()
      if (props.mode === 'replay') {
        startReplay()
      } else if (!connected.value) {
        connect()
      }
      setTimeout(() => { if (fitAddon) fitAddon.fit() }, 100)
    })
  } else {
    if (props.mode === 'replay') {
      stopReplay()
    } else {
      disconnect()
    }
  }
})

watch(() => props.ticketDbId, (newVal, oldVal) => {
  if (newVal !== oldVal) {
    stopReplay()
    disconnect()
    if (term) term.clear()
    if (props.visible) {
      nextTick(() => {
        initTerminal()
        if (props.mode === 'replay') {
          startReplay()
        } else {
          connect()
        }
      })
    }
  }
})

// 当 replayLogs 变化时重新开始回放
watch(() => props.replayLogs, (newLogs) => {
  if (props.mode === 'replay' && props.visible && newLogs?.length) {
    nextTick(() => {
      initTerminal()
      startReplay()
    })
  }
}, { deep: false })

onMounted(() => {
  if (props.visible) {
    nextTick(() => {
      initTerminal()
      if (props.mode === 'replay') {
        startReplay()
      } else {
        connect()
      }
    })
  }
})

onBeforeUnmount(() => {
  stopReplay()
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
  background: var(--text-muted);
  transition: all 0.3s;
}

.terminal-dot.connected {
  background: #9ece6a;
  animation: pulse 2s ease-in-out infinite;
  box-shadow: 0 0 8px rgba(158, 206, 106, 0.4);
}

.terminal-dot.replay {
  background: #7aa2f7;
  animation: pulse 2s ease-in-out infinite;
  box-shadow: 0 0 8px rgba(122, 162, 247, 0.4);
}

.terminal-dot.error {
  background: #f7768e;
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

.replay-anim {
  display: inline-block;
  animation: blink 1s step-end infinite;
}

@keyframes blink {
  50% { opacity: 0; }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
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

<template>
  <t-card title="自动化链接" :bordered="false">
    <template #actions>
      <t-button theme="primary" type="button" aria-haspopup="dialog" :disabled="loading || busy" @click="emit('connect', $event)">
        <template #icon><t-icon name="add" aria-hidden="true" /></template>
        {{ connectLabel }}
      </t-button>
    </template>

    <div class="connections-body">
      <p class="connections-progress" role="status" aria-atomic="true">
        {{ loading ? '正在加载连接…' : busy ? '正在处理连接…' : '' }}
      </p>

      <div v-if="!connections.length && !loading" class="connections-empty">
        <h3>暂无自动化链接</h3>
        <p>{{ emptyDescription }}</p>
      </div>

      <ul v-else-if="connections.length" class="connections-list" role="list" aria-label="账号连接列表" :aria-busy="loading">
        <li v-for="connection in connections" :key="connection.id" class="connection-row">
          <div class="connection-identity">
            <div class="connection-heading">
              <h3>{{ connection.label }}</h3>
              <span class="connection-status" :data-status="connection.status">
                <span class="connection-status-dot" aria-hidden="true"></span>
                {{ connectionStatusLabels[connection.status] }}
              </span>
            </div>
            <p v-if="connection.workspace">工作区<span>{{ connection.workspace }}</span></p>
          </div>

          <dl class="connection-dates">
            <div>
              <dt>最近更新</dt>
              <dd>
                <time v-if="connection.lastUpdated" :datetime="connection.lastUpdated">
                  {{ formatConnectionTime(connection.lastUpdated) }}
                </time>
                <span v-else>—</span>
              </dd>
            </div>
            <div>
              <dt>访问凭据到期</dt>
              <dd>
                <time v-if="connection.expiresAt" :datetime="connection.expiresAt">
                  {{ formatConnectionTime(connection.expiresAt) }}
                </time>
                <span v-else>—</span>
              </dd>
            </div>
          </dl>

          <div class="connection-actions">
            <t-button
              type="button"
              variant="outline"
              :disabled="loading || busy"
              :aria-disabled="connection.status === 'connecting' ? 'true' : undefined"
              :aria-label="`${connection.status === 'connected' ? openLabel : primaryActionLabels[connection.status]} ${connectionName(connection)}`"
              @click="handlePrimaryAction(connection, $event)"
            >
              {{ connection.status === 'connected' ? openLabel : primaryActionLabels[connection.status] }}
            </t-button>
            <t-button
              v-if="connection.status !== 'disconnected'"
              type="button"
              variant="text"
              :disabled="loading || busy || connection.status === 'connecting'"
              :aria-label="`解除连接 ${connectionName(connection)}`"
              @click="emit('disconnect', connection.id, $event)"
            >
              解除连接
            </t-button>
          </div>
        </li>
      </ul>
    </div>
  </t-card>
</template>

<script setup lang="ts">
import {
  connectionStatusLabels,
  formatConnectionTime,
  type ConnectionStatus,
  type ExternalConnection,
} from '../connection-details'

const props = withDefaults(defineProps<{
  connections: readonly ExternalConnection[]
  loading?: boolean
  busy?: boolean
  connectLabel?: string
  openLabel?: string
  emptyDescription?: string
}>(), {
  loading: false,
  busy: false,
  connectLabel: '发起连接',
  openLabel: '进入',
  emptyDescription: '发起连接后，账号及其连接状态会显示在这里。',
})

const emit = defineEmits<{
  connect: [event: MouseEvent, id?: string]
  open: [id: string, event: MouseEvent]
  reconnect: [id: string]
  disconnect: [id: string, event: MouseEvent]
}>()

const primaryActionLabels: Record<ConnectionStatus, string> = {
  connected: '进入',
  disconnected: '连接',
  connecting: '重新连接',
  'needs-reconnect': '重新连接',
  unavailable: '重新连接',
}

const connectionName = ({ label, workspace }: ExternalConnection) =>
  workspace ? `${label}（${workspace}）` : label

function handlePrimaryAction(connection: ExternalConnection, event: MouseEvent) {
  if (props.loading || props.busy || connection.status === 'connecting') return

  if (connection.status === 'connected') {
    emit('open', connection.id, event)
  } else if (connection.status === 'disconnected') {
    emit('connect', event, connection.id)
  } else {
    emit('reconnect', connection.id)
  }
}
</script>

<style scoped>
.connections-body {
  min-width: 0;
  container-type: inline-size;
}

.connections-progress {
  margin: 0 0 10px;
  color: var(--app-text-muted);
  font-size: 13px;
  line-height: 1.5;
}

.connections-progress:empty { margin: 0; }

.connections-list {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.connection-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  align-items: center;
  gap: 12px 18px;
  padding: 14px;
  border: 1px solid var(--app-border);
  border-radius: 10px;
  background: var(--app-field);
}

.connection-heading,
.connection-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 7px 9px;
}

.connection-heading h3,
.connections-empty h3 {
  min-width: 0;
  margin: 0;
  color: var(--app-text);
  font-size: 14px;
  font-weight: 640;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.connection-identity p,
.connections-empty p {
  margin: 5px 0 0;
  color: var(--app-text-muted);
  font-size: 13px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.connection-identity p span { margin-inline-start: 6px; }

.connection-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 1px 7px;
  border: 1px solid var(--app-border);
  border-radius: 5px;
  color: var(--app-text-muted);
  background: var(--app-surface);
  font-size: 12px;
  line-height: 1.55;
}

.connection-status-dot {
  box-sizing: border-box;
  flex: 0 0 7px;
  width: 7px;
  height: 7px;
  border: 1px solid currentColor;
  border-radius: 50%;
}

.connection-status[data-status='connected'] .connection-status-dot { background: currentColor; }
.connection-status[data-status='connecting'] .connection-status-dot { border-style: dotted; }
.connection-status[data-status='needs-reconnect'] .connection-status-dot { border-radius: 1px; }
.connection-status[data-status='unavailable'] .connection-status-dot {
  height: 1px;
  border: 0;
  background: currentColor;
}

.connection-dates {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 118px), 1fr));
  gap: 8px 12px;
  margin: 0;
  color: var(--app-text-muted);
  font-size: 12px;
  line-height: 1.5;
}

.connection-dates dd {
  margin: 3px 0 0;
  color: var(--app-text);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}

.connections-empty {
  padding: clamp(18px, 4vw, 28px) 14px;
  border: 1px solid var(--app-border);
  border-radius: 10px;
  background: var(--app-field);
  text-align: center;
}

:deep(.t-button:focus-visible) {
  outline: 2px solid var(--app-action);
  outline-offset: 2px;
}

.connection-actions :deep(.t-button[aria-disabled='true']) {
  color: var(--app-text-muted);
  background: var(--app-field);
  border-color: var(--app-border);
  cursor: wait;
}

@container (min-width: 680px) {
  .connection-row {
    grid-template-columns: minmax(145px, 1fr) minmax(248px, 1.2fr) max-content;
  }

  .connection-actions { justify-content: flex-end; }
}

@media (max-width: 620px) {
  :deep(.t-button) { min-height: 44px; }
}
</style>

<template>
  <div>
    <t-card title="公告" subtitle="向所有用户或指定用户发布登录公告" :bordered="false">
      <template #actions>
        <t-space>
          <t-button variant="outline" :loading="loading" @click="fetchData">刷新</t-button>
          <t-button theme="primary" @click="showCreateDialog">
            <template #icon><t-icon name="add" /></template>
            发布公告
          </t-button>
        </t-space>
      </template>

      <t-tabs v-model="activeListTab" class="announcement-tabs">
        <t-tab-panel value="current" :label="`当前公告 (${currentAnnouncements.length})`" />
        <t-tab-panel value="scheduled" :label="`待发布 (${scheduledAnnouncements.length})`" />
        <t-tab-panel value="history" :label="`历史公告 (${historyAnnouncements.length})`" />
      </t-tabs>

      <t-table :data="visibleAnnouncements" :columns="columns" :loading="loading" row-key="id">
        <template #scope="{ row }">
          <t-tag :theme="row.scope === 'global' ? 'primary' : 'warning'" variant="light">
            {{ row.scope === 'global' ? '全局公告' : '个人公告' }}
          </t-tag>
        </template>
        <template #target="{ row }">
          {{ row.scope === 'global' ? '所有用户' : row.target_username || '-' }}
        </template>
        <template #content="{ row }">
          <span class="content-preview">{{ row.content }}</span>
        </template>
        <template #status="{ row }">
          <t-tag :theme="statusMeta(row.status).theme">
            {{ statusMeta(row.status).label }}
          </t-tag>
        </template>
        <template #schedule="{ row }">
          <div class="schedule-cell">
            <span>{{ formatDate(row.start_at, row.display_timezone) }}</span>
            <span>至 {{ row.end_at ? formatDate(row.end_at, row.display_timezone) : '长期' }}</span>
            <small>{{ row.display_timezone }}</small>
          </div>
        </template>
        <template #updated_at="{ row }">
          {{ formatDate(row.updated_at) }}
        </template>
        <template #op="{ row }">
          <t-space>
            <t-link theme="primary" @click="showEditDialog(row)">编辑</t-link>
            <t-link theme="primary" @click="toggleAnnouncement(row)">
              {{ row.is_active ? '停用' : '启用' }}
            </t-link>
            <t-popconfirm content="确定删除该公告吗？" @confirm="deleteAnnouncement(row)">
              <t-link theme="danger">删除</t-link>
            </t-popconfirm>
          </t-space>
        </template>
      </t-table>

      <t-empty v-if="!loading && visibleAnnouncements.length === 0" description="当前分类暂无公告" />
    </t-card>

    <t-dialog
      :visible="dialogVisible"
      :header="isEdit ? '编辑公告' : '发布公告'"
      :confirm-btn="{ content: isEdit ? '保存' : '发布', loading: saving }"
      width="1040px"
      @confirm="saveAnnouncement"
      @close="dialogVisible = false"
    >
      <t-form :data="formData" label-width="92px">
        <t-form-item label="标题" name="title">
          <t-input
            v-model="formData.title"
            :maxlength="120"
            show-limit-number
            placeholder="请输入公告标题"
          />
        </t-form-item>
        <t-form-item label="发布范围" name="scope">
          <t-radio-group v-model="formData.scope" variant="default-filled">
            <t-radio-button value="global">所有用户</t-radio-button>
            <t-radio-button value="personal">指定用户</t-radio-button>
          </t-radio-group>
        </t-form-item>
        <t-form-item v-if="formData.scope === 'personal'" label="目标用户" name="target_user_id">
          <t-select
            v-model="formData.target_user_id"
            filterable
            clearable
            placeholder="请选择用户"
          >
            <t-option
              v-for="user in userOptions"
              :key="user.id"
              :value="user.id"
              :label="user.username"
            />
          </t-select>
        </t-form-item>
        <div class="schedule-form-grid">
          <t-form-item label="显示时区" name="display_timezone">
            <t-select v-model="formData.display_timezone" filterable>
              <t-option
                v-for="timezone in timezoneOptions"
                :key="timezone.value"
                :value="timezone.value"
                :label="timezone.label"
              />
            </t-select>
          </t-form-item>
          <t-form-item label="开始时间" name="start_at">
            <t-date-picker
              v-model="formData.start_at"
              enable-time-picker
              clearable
              format="YYYY-MM-DD HH:mm:ss"
              value-type="YYYY-MM-DD HH:mm:ss"
              placeholder="留空表示立即开始"
            />
          </t-form-item>
          <t-form-item label="结束时间" name="end_at">
            <t-date-picker
              v-model="formData.end_at"
              enable-time-picker
              clearable
              format="YYYY-MM-DD HH:mm:ss"
              value-type="YYYY-MM-DD HH:mm:ss"
              placeholder="留空表示长期有效"
            />
          </t-form-item>
        </div>
        <t-form-item label="公告内容" name="content">
          <div class="announcement-editor">
            <div class="announcement-editor__input">
              <div class="editor-pane-title">Markdown 编辑</div>
              <t-textarea
                v-model="formData.content"
                :maxlength="10000"
                :autosize="{ minRows: 12, maxRows: 16 }"
                placeholder="请输入 Markdown 格式的公告内容"
              />
              <div class="form-help">
                支持标题、列表、链接、引用、代码块、表格和图片；原始 HTML 不会执行。
              </div>
            </div>
            <section class="announcement-editor__preview" aria-label="公告实时预览">
              <div class="editor-pane-title">实时预览</div>
              <div class="announcement-preview">
                <h3 v-if="formData.title.trim()" class="preview-title">{{ formData.title }}</h3>
                <div v-else class="preview-placeholder">公告标题将显示在这里</div>
                <MarkdownContent v-if="formData.content.trim()" :content="formData.content" />
                <div v-else class="preview-placeholder">开始输入后，此处将实时显示公告内容。</div>
              </div>
            </section>
          </div>
        </t-form-item>
        <t-form-item label="立即发布" name="is_active">
          <t-switch v-model="formData.is_active" />
          <template #help>
            <span class="form-help">启用后仅在设定的开始和结束时间内作为当前公告展示；到期后自动进入历史公告。</span>
          </template>
        </t-form-item>
      </t-form>
    </t-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { MessagePlugin } from 'tdesign-vue-next'
import request from '@/api/request'
import MarkdownContent from '@/components/MarkdownContent.vue'

type AnnouncementScope = 'global' | 'personal'

type Announcement = {
  id: number
  title: string
  content: string
  scope: AnnouncementScope
  target_user_id: number | null
  target_username?: string
  is_active: boolean
  start_at: string
  end_at: string | null
  display_timezone: string
  status: 'current' | 'scheduled' | 'history' | 'disabled'
  updated_at: string
}

type UserOption = {
  id: number
  username: string
}

const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const activeListTab = ref<'current' | 'scheduled' | 'history'>('current')
const tableData = ref<Announcement[]>([])
const userOptions = ref<UserOption[]>([])

const columns = [
  { colKey: 'id', title: 'ID', width: 72 },
  { colKey: 'title', title: '标题', width: 220, ellipsis: true },
  { colKey: 'scope', title: '范围', cell: 'scope', width: 110 },
  { colKey: 'target', title: '目标用户', cell: 'target', width: 150 },
  { colKey: 'content', title: '内容', cell: 'content', ellipsis: true },
  { colKey: 'status', title: '状态', cell: 'status', width: 90 },
  { colKey: 'schedule', title: '生效时间', cell: 'schedule', width: 220 },
  { colKey: 'updated_at', title: '更新时间', cell: 'updated_at', width: 170 },
  { colKey: 'op', title: '操作', cell: 'op', width: 170 },
]

const formData = reactive({
  id: 0,
  title: '',
  content: '',
  scope: 'global' as AnnouncementScope,
  target_user_id: null as number | null,
  is_active: true,
  start_at: '',
  end_at: '',
  display_timezone: 'Asia/Shanghai',
})

const timezoneOptions = [
  { label: '中国标准时间 · Asia/Shanghai', value: 'Asia/Shanghai' },
  { label: '香港时间 · Asia/Hong_Kong', value: 'Asia/Hong_Kong' },
  { label: '日本时间 · Asia/Tokyo', value: 'Asia/Tokyo' },
  { label: '协调世界时 · UTC', value: 'UTC' },
  { label: '英国时间 · Europe/London', value: 'Europe/London' },
  { label: '美国东部时间 · America/New_York', value: 'America/New_York' },
  { label: '美国西部时间 · America/Los_Angeles', value: 'America/Los_Angeles' },
]

const currentAnnouncements = computed(() => tableData.value.filter(item => item.status === 'current'))
const scheduledAnnouncements = computed(() => tableData.value.filter(item => item.status === 'scheduled'))
const historyAnnouncements = computed(() => tableData.value.filter(item => ['history', 'disabled'].includes(item.status)))
const visibleAnnouncements = computed(() => {
  if (activeListTab.value === 'scheduled') return scheduledAnnouncements.value
  if (activeListTab.value === 'history') return historyAnnouncements.value
  return currentAnnouncements.value
})

const fetchData = async () => {
  loading.value = true
  const data = await request('/0x/user/announcements')
  loading.value = false
  if (!data) return

  tableData.value = data.results || []
  userOptions.value = data.users || []
}

onMounted(fetchData)

const resetForm = () => {
  Object.assign(formData, {
    id: 0,
    title: '',
    content: '',
    scope: 'global',
    target_user_id: null,
    is_active: true,
    start_at: '',
    end_at: '',
    display_timezone: 'Asia/Shanghai',
  })
}

const showCreateDialog = () => {
  isEdit.value = false
  resetForm()
  dialogVisible.value = true
}

const showEditDialog = (row: Announcement) => {
  isEdit.value = true
  Object.assign(formData, {
    id: row.id,
    title: row.title,
    content: row.content,
    scope: row.scope,
    target_user_id: row.target_user_id,
    is_active: row.is_active,
    display_timezone: row.display_timezone || 'Asia/Shanghai',
    start_at: formatDateInput(row.start_at, row.display_timezone || 'Asia/Shanghai'),
    end_at: row.end_at ? formatDateInput(row.end_at, row.display_timezone || 'Asia/Shanghai') : '',
  })
  dialogVisible.value = true
}

const announcementPayload = (overrides: Partial<Announcement> = {}) => ({
  id: formData.id,
  title: formData.title.trim(),
  content: formData.content.trim(),
  scope: formData.scope,
  target_user_id: formData.scope === 'personal' ? formData.target_user_id : null,
  is_active: formData.is_active,
  start_at: formData.start_at ? zonedDateTimeToIso(formData.start_at, formData.display_timezone) : null,
  end_at: formData.end_at ? zonedDateTimeToIso(formData.end_at, formData.display_timezone) : null,
  display_timezone: formData.display_timezone,
  ...overrides,
})

const validateForm = () => {
  if (!formData.title.trim()) {
    MessagePlugin.warning('请输入公告标题')
    return false
  }
  if (!formData.content.trim()) {
    MessagePlugin.warning('请输入公告内容')
    return false
  }
  if (formData.scope === 'personal' && !formData.target_user_id) {
    MessagePlugin.warning('请选择目标用户')
    return false
  }
  if (formData.start_at && formData.end_at) {
    const start = zonedDateTimeToIso(formData.start_at, formData.display_timezone)
    const end = zonedDateTimeToIso(formData.end_at, formData.display_timezone)
    if (new Date(end).getTime() <= new Date(start).getTime()) {
      MessagePlugin.warning('结束时间必须晚于开始时间')
      return false
    }
  }
  return true
}

const saveAnnouncement = async () => {
  if (!validateForm()) return

  saving.value = true
  const data = await request(
    '/0x/user/announcements',
    isEdit.value ? 'PUT' : 'POST',
    announcementPayload(),
  )
  saving.value = false
  if (!data) return

  MessagePlugin.success(isEdit.value ? '公告已更新' : '公告已发布')
  dialogVisible.value = false
  await fetchData()
}

const toggleAnnouncement = async (row: Announcement) => {
  const data = await request('/0x/user/announcements', 'PUT', {
    id: row.id,
    title: row.title,
    content: row.content,
    scope: row.scope,
    target_user_id: row.target_user_id,
    is_active: !row.is_active,
    start_at: row.start_at,
    end_at: row.end_at,
    display_timezone: row.display_timezone,
  })
  if (!data) return

  MessagePlugin.success(row.is_active ? '公告已停用' : '公告已启用')
  await fetchData()
}

const deleteAnnouncement = async (row: Announcement) => {
  const data = await request('/0x/user/announcements', 'DELETE', { id: row.id })
  if (!data) return

  MessagePlugin.success('公告已删除')
  await fetchData()
}

const statusMeta = (status: Announcement['status']) => ({
  current: { label: '当前', theme: 'success' },
  scheduled: { label: '待发布', theme: 'primary' },
  history: { label: '已结束', theme: 'default' },
  disabled: { label: '已停用', theme: 'default' },
}[status] || { label: '未知', theme: 'default' })

const formatDate = (value: string, timeZone = 'Asia/Shanghai') => {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN', { hour12: false, timeZone })
}

const formatDateInput = (value: string, timeZone: string) => {
  if (!value) return ''
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }).formatToParts(new Date(value))
  const part = (type: string) => parts.find(item => item.type === type)?.value || ''
  return `${part('year')}-${part('month')}-${part('day')} ${part('hour')}:${part('minute')}:${part('second')}`
}

const zonedDateTimeToIso = (value: string, timeZone: string) => {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?$/)
  if (!match) return value
  const desired = Date.UTC(+match[1], +match[2] - 1, +match[3], +match[4], +match[5], +(match[6] || 0))
  let guess = desired
  for (let index = 0; index < 3; index += 1) {
    const shown = formatDateInput(new Date(guess).toISOString(), timeZone)
    const shownMatch = shown.match(/^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})$/)
    if (!shownMatch) break
    const shownUtc = Date.UTC(+shownMatch[1], +shownMatch[2] - 1, +shownMatch[3], +shownMatch[4], +shownMatch[5], +shownMatch[6])
    guess += desired - shownUtc
  }
  return new Date(guess).toISOString()
}
</script>

<style scoped>
.content-preview {
  display: block;
  max-width: 420px;
  overflow: hidden;
  color: var(--app-text-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.form-help {
  margin-top: 8px;
  color: var(--app-text-muted);
  font-size: 13px;
  line-height: 1.5;
}

.announcement-tabs {
  margin-bottom: 16px;
}

.schedule-cell {
  display: grid;
  gap: 2px;
  color: var(--app-text);
  font-size: 12px;
  line-height: 1.5;
}

.schedule-cell small {
  color: var(--app-text-muted);
}

.schedule-form-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
}

.announcement-editor {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 20px;
  width: 100%;
}

.announcement-editor__input,
.announcement-editor__preview {
  min-width: 0;
}

.editor-pane-title {
  margin-bottom: 8px;
  color: var(--app-text);
  font-size: 13px;
  font-weight: 600;
}

.announcement-preview {
  height: 330px;
  padding: 14px 16px;
  overflow-y: auto;
  border: 1px solid var(--td-component-border);
  border-radius: 6px;
  background: var(--td-bg-color-container);
}

.preview-title {
  margin: 0 0 12px;
  color: var(--app-text);
  font-size: 16px;
  font-weight: 600;
  line-height: 1.5;
}

.preview-placeholder {
  color: var(--app-text-muted);
  font-size: 13px;
  line-height: 1.7;
}

.preview-title + .preview-placeholder {
  margin-top: 4px;
}

@media (max-width: 900px) {
  .schedule-form-grid {
    grid-template-columns: 1fr;
  }

  .announcement-editor {
    grid-template-columns: 1fr;
  }

  .announcement-preview {
    height: auto;
    min-height: 220px;
    max-height: 360px;
  }
}
</style>

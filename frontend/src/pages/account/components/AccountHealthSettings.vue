<template>
  <t-button variant="outline" @click="open">定时健康检测</t-button>
  <t-dialog v-model:visible="visible" header="定时健康检测与邮件通知" width="min(680px, 94vw)" placement="center"
    :confirm-btn="{ content: '保存设置', loading: saving, disabled: loading || testing }" @confirm="save">
    <t-loading :loading="loading">
      <t-form label-width="110px" class="health-settings">
        <t-form-item label="开启检测"><t-switch v-model="form.enabled" /></t-form-item>
        <t-form-item label="检测间隔">
          <t-input-number v-model="form.interval_minutes" :min="2" :max="10080" :decimal-places="0" />
          <span class="field-note">分钟（最短 2 分钟）</span>
        </t-form-item>
        <p class="help-text">首次异常后等待 18 秒复检，仍异常才通知。持续异常只通知一次，恢复后再次异常会重新通知；发信失败每 2 分钟重试。</p>
        <t-form-item label="收件邮箱"><t-input v-model="form.recipient" placeholder="接收异常通知的邮箱" /></t-form-item>
        <t-form-item label="收件测试">
          <t-checkbox v-model="testOnChange">首次设置或更换收件邮箱时发送 test 邮件（可取消）</t-checkbox>
        </t-form-item>
        <t-divider>SMTP · 发送通知</t-divider>
        <t-form-item label="邮箱服务商">
          <t-select v-model="provider" :options="providerOptions" @change="applyProvider" />
        </t-form-item>
        <p class="help-text">QQ / 网易请使用客户端授权码，iCloud 请使用 App 专用密码。</p>
        <t-form-item label="SMTP 服务器"><t-input v-model="form.smtp_host" placeholder="smtp.example.com" /></t-form-item>
        <t-form-item label="连接方式">
          <t-space break-line>
            <t-select v-model="form.smtp_security" :options="securityOptions" style="width: 150px" />
            <t-input-number v-model="form.smtp_port" aria-label="SMTP 端口" :min="1" :max="65535" :decimal-places="0" />
          </t-space>
        </t-form-item>
        <t-form-item label="发件邮箱"><t-input v-model="form.smtp_username" placeholder="同时作为 SMTP 登录用户名" /></t-form-item>
        <t-form-item label="SMTP 授权码">
          <input v-model="form.smtp_password" class="secret-input" type="password" autocomplete="new-password"
            aria-label="SMTP 授权码" :placeholder="form.smtp_configured ? '已配置；留空保留，输入新值覆盖' : '填写邮箱授权码或应用密码'" />
        </t-form-item>
        <t-collapse :default-value="[]">
          <t-collapse-panel value="imap" header="IMAP 配置（可选，不影响 SMTP 发信）">
            <t-form-item label="IMAP 服务器"><t-input v-model="form.imap_host" placeholder="imap.example.com" /></t-form-item>
            <t-form-item label="连接方式">
              <t-space break-line>
                <t-select v-model="form.imap_security" :options="securityOptions" style="width: 150px" />
                <t-input-number v-model="form.imap_port" aria-label="IMAP 端口" :min="1" :max="65535" :decimal-places="0" />
              </t-space>
            </t-form-item>
            <t-form-item label="IMAP 用户名"><t-input v-model="form.imap_username" placeholder="邮箱登录用户名" /></t-form-item>
            <t-form-item label="IMAP 授权码">
              <input v-model="form.imap_password" class="secret-input" type="password" autocomplete="new-password"
                aria-label="IMAP 授权码" :placeholder="form.imap_configured ? '已配置；留空保留，输入新值覆盖' : '填写邮箱授权码或应用密码'" />
            </t-form-item>
            <t-button variant="outline" :loading="testing" :disabled="saving" @click="test('test_imap')">测试已保存的 IMAP 配置</t-button>
          </t-collapse-panel>
        </t-collapse>
        <p class="help-text">授权码加密保存，保存后不回显。更换服务器、端口、连接方式或用户名时，需重新填写授权码。检测覆盖全部上游账号，至少一种登录凭据可用即视为正常。</p>
        <t-space direction="vertical">
          <t-button variant="outline" :loading="testing" :disabled="saving" @click="test('test_mail')">发送测试邮件（使用已保存配置）</t-button>
          <span v-if="form.last_sent_at" class="help-text">最近发送：{{ new Date(form.last_sent_at).toLocaleString() }}</span>
          <t-alert v-if="form.last_mail_error" theme="warning" :message="form.last_mail_error" />
        </t-space>
      </t-form>
    </t-loading>
  </t-dialog>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { MessagePlugin } from 'tdesign-vue-next'
import request from '@/api/request'

const visible = ref(false)
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const testOnChange = ref(true)
const provider = ref('custom')
const providerOptions = [
  { label: '自定义 SMTP', value: 'custom' }, { label: 'QQ 邮箱', value: 'qq' },
  { label: '163 邮箱', value: '163' }, { label: '126 邮箱', value: '126' },
  { label: 'iCloud 邮箱', value: 'icloud' }
]
const presets: Record<string, { smtp_host: string; smtp_port: number; smtp_security: string }> = {
  qq: { smtp_host: 'smtp.qq.com', smtp_port: 465, smtp_security: 'ssl' },
  '163': { smtp_host: 'smtp.163.com', smtp_port: 465, smtp_security: 'ssl' },
  '126': { smtp_host: 'smtp.126.com', smtp_port: 465, smtp_security: 'ssl' },
  icloud: { smtp_host: 'smtp.mail.me.com', smtp_port: 587, smtp_security: 'starttls' }
}
const securityOptions = [{ label: 'SSL / TLS', value: 'ssl' }, { label: 'STARTTLS', value: 'starttls' }]
const form = reactive({
  enabled: false, interval_minutes: 5, recipient: '', revision: 0,
  smtp_host: '', smtp_port: 465, smtp_security: 'ssl', smtp_username: '', smtp_password: '', smtp_configured: false,
  imap_host: '', imap_port: 993, imap_security: 'ssl', imap_username: '', imap_password: '', imap_configured: false,
  last_sent_at: '', last_mail_error: ''
})
watch(visible, (value) => {
  if (!value) { form.smtp_password = ''; form.imap_password = '' }
})
function applyProvider(value: unknown) {
  const preset = typeof value === 'string' ? presets[value] : undefined
  if (preset) Object.assign(form, preset)
}
async function open() {
  visible.value = true
  loading.value = true
  const data = await request('/0x/chatgpt/health-settings')
  loading.value = false
  if (!data) { visible.value = false; return }
  Object.assign(form, data, { smtp_password: '', imap_password: '' })
  provider.value = Object.keys(presets).find((key) => presets[key].smtp_host === form.smtp_host) || 'custom'
  testOnChange.value = true
}
async function save() {
  if (saving.value || loading.value || testing.value) return
  saving.value = true
  const data = await request('/0x/chatgpt/health-settings', 'PUT', {
    ...form, test_on_recipient_change: testOnChange.value
  })
  saving.value = false
  if (!data) return
  Object.assign(form, data, { smtp_password: '', imap_password: '' })
  MessagePlugin.success(data.message)
  visible.value = false
}
async function test(action: string) {
  if (testing.value || saving.value) return
  testing.value = true
  const data = await request('/0x/chatgpt/health-settings', 'POST', { action })
  testing.value = false
  if (data) MessagePlugin.success(data.message)
}
</script>

<style scoped>
.health-settings { max-height: min(68vh, calc(100dvh - 180px)); overflow-y: auto; padding: 4px 12px 4px 0; }
.help-text { color: var(--td-text-color-secondary); font-size: 13px; line-height: 1.6; margin: 12px 0; }
.field-note { margin-left: 8px; color: var(--td-text-color-secondary); }
.secret-input { box-sizing: border-box; width: 100%; height: 32px; padding: 0 8px; border: 1px solid var(--td-border-level-2-color); border-radius: var(--td-radius-default); color: var(--td-text-color-primary); background: var(--td-bg-color-container); font: inherit; }
.secret-input:focus-visible { outline: 2px solid var(--td-brand-color); outline-offset: 1px; }
@media (max-width: 600px) {
  .health-settings :deep(.t-form__label) { float: none; width: auto !important; text-align: left; }
  .health-settings :deep(.t-form__controls) { margin-left: 0 !important; }
  .health-settings :deep(.t-form__controls-content) { flex-wrap: wrap; }
}
</style>

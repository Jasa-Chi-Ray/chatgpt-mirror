<template>
  <t-card :title="t('Linux DO 登录')" :subtitle="t('绑定后可通过 Linux DO 登录当前镜像账号')" :bordered="false">
    <t-loading :loading="loading">
      <p v-if="loading" class="connection-description">{{ t('正在读取绑定状态') }}</p>
      <p v-else-if="loadFailed" class="connection-description">{{ t('无法读取绑定状态，请重试。') }} <t-button variant="text" @click="load">{{ t('重新读取') }}</t-button></p>
      <template v-else>
      <p class="connection-status">{{ t(connection.linked ? '已绑定' : '未绑定') }}<strong v-if="connection.linked"> · {{ connection.username }}</strong></p>
      <p v-if="!connection.enabled" class="connection-description">{{ t('本站尚未启用 Linux DO 登录，请联系管理员配置环境变量。') }}</p>
      <p v-else-if="connection.linked && !connection.can_unlink" class="connection-description">{{ t('此账号通过 Linux DO 注册。需要解除绑定时，请先由管理员设置本地密码。') }}</p>
      <p v-else class="connection-description">{{ t('每个镜像账号可绑定一个 Linux DO 账号，绑定信息仅向账号本人展示。') }}</p>
      <t-button v-if="!connection.linked" :disabled="!connection.enabled" :loading="busy" @click="link">{{ t('绑定 Linux DO') }}</t-button>
      <t-button v-else theme="default" :disabled="!connection.can_unlink" :loading="busy" @click="confirmUnlink">{{ t('解除绑定') }}</t-button>
      </template>
    </t-loading>
  </t-card>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { DialogPlugin, MessagePlugin } from 'tdesign-vue-next'
import { linuxdoError, linuxdoRequest } from '@/api/linuxdo'
import { useUserStore } from '@/store/user'
import { useWorkspaceCopy } from '@/pages/account/workspace-copy'

const { t } = useWorkspaceCopy()
const store = useUserStore()
const route = useRoute()
const router = useRouter()
const loading = ref(true)
const loadFailed = ref(false)
const busy = ref(false)
const connection = reactive({ enabled: false, linked: false, username: '', can_unlink: false })

const load = async () => {
  loading.value = true
  loadFailed.value = false
  try { Object.assign(connection, await linuxdoRequest('connection', store.csrfToken, undefined, 'GET')) }
  catch (error: any) { loadFailed.value = true; MessagePlugin.error(t(error.message)) }
  finally { loading.value = false }
}

const link = async () => {
  if (busy.value) return
  busy.value = true
  try {
    const data = await store.startLinuxDO('link')
    window.location.assign(data.authorize_url)
  } catch (error: any) { MessagePlugin.error(t(error.message)); busy.value = false }
}

const confirmUnlink = () => {
  const dialog = DialogPlugin.confirm({
    header: t('解除 Linux DO 绑定'),
    body: t('解除后请使用本地用户名和密码登录。确认继续？'),
    confirmBtn: t('解除绑定'), cancelBtn: t('取消'),
    onConfirm: async () => {
      if (busy.value) return
      busy.value = true
      try {
        await linuxdoRequest('connection', store.csrfToken, undefined, 'DELETE')
        dialog.destroy()
        MessagePlugin.success(t('绑定已解除'))
        await load()
      } catch (error: any) { MessagePlugin.error(t(error.message)) }
      finally { busy.value = false }
    }
  })
}

onMounted(async () => {
  const ticket = route.query.linuxdo_result
  const errorCode = route.query.linuxdo_error
  if (ticket || errorCode) await router.replace({ path: route.path, query: {} })
  if (errorCode) MessagePlugin.error(t(linuxdoError(errorCode)))
  if (typeof ticket === 'string') {
    busy.value = true
    try {
      const data = await store.completeLinuxDO(ticket)
      if (data.linked) MessagePlugin.success(t('Linux DO 绑定成功'))
    } catch (error: any) { MessagePlugin.error(t(error.message)) }
    finally { busy.value = false }
  }
  await load()
})
</script>

<style scoped>
.connection-status { margin: 0 0 8px; color: var(--app-text); font-size: 14px; }
.connection-description { margin: 0 0 20px; color: var(--app-text-muted); font-size: 13px; line-height: 1.7; }
</style>

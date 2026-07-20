<template>
  <div class="layout">
    <t-layout>
      <t-aside>
        <div class="logo">
          <span class="logo-bear" aria-hidden="true">🐻</span>
          <span>ChatGPT Mirror</span>
        </div>
        <t-menu :value="activeMenu" theme="dark" @change="handleMenuChange">
          <t-menu-item value="/account/user">
            <template #icon><t-icon name="user" /></template>
            用户管理
          </t-menu-item>
          <t-menu-item value="/account/chatgpt">
            <template #icon><span class="menu-bear" aria-hidden="true">🐻</span></template>
            ChatGPT账号
          </t-menu-item>
          <t-menu-item value="/account/gptcar">
            <template #icon><t-icon name="server" /></template>
            号池管理
          </t-menu-item>
          <t-menu-item value="/account/logs">
            <template #icon><t-icon name="file" /></template>
            访问日志
          </t-menu-item>
          <t-menu-item value="/account/proxy">
            <template #icon><t-icon name="internet" /></template>
            代理
          </t-menu-item>
          <t-menu-item value="/account/scripts">
            <template #icon><t-icon name="code" /></template>
            脚本
          </t-menu-item>
          <t-menu-item value="/account/access">
            <template #icon><t-icon name="secured" /></template>
            访问限制
          </t-menu-item>
        </t-menu>
      </t-aside>
      <t-layout>
        <t-header class="header">
          <div class="header-right">
            <t-dropdown :options="userOptions" @click="handleUserAction">
              <t-button variant="text">
                <t-icon name="user-circle" />
                {{ username }}
              </t-button>
            </t-dropdown>
          </div>
        </t-header>
        <t-content class="content">
          <router-view />
          <div class="layout-footer">制作者:Xiaoxiong</div>
        </t-content>
      </t-layout>
    </t-layout>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const activeMenu = computed(() => route.path)
const username = computed(() => userStore.username || '管理员')

const userOptions = [
  { content: '退出登录', value: 'logout' }
]

const handleMenuChange = (value: string) => {
  router.push(value)
}

const handleUserAction = (data: { value: string }) => {
  if (data.value === 'logout') {
    userStore.logout()
    router.push('/login')
  }
}
</script>

<style scoped>
.layout {
  height: 100vh;
}

.logo {
  display: flex;
  align-items: center;
  padding: 16px;
  color: #fff;
  font-size: 18px;
  font-weight: bold;
}

.logo-bear {
  display: inline-flex;
  width: 32px;
  height: 32px;
  margin-right: 8px;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  line-height: 1;
}

.menu-bear {
  display: inline-flex;
  width: 32px;
  height: 32px;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  line-height: 1;
}

.header {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  padding: 0 24px;
  background: #fff;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.1);
}

.header-right {
  display: flex;
  align-items: center;
}

.content {
  padding: 24px;
  background: #f5f5f5;
  min-height: calc(100vh - 64px);
}

.layout-footer {
  margin-top: 24px;
  text-align: center;
  color: #6b7280;
  font-size: 12px;
}
</style>

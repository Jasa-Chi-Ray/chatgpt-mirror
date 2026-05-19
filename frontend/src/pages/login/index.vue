<template>
  <div style="display: flex; flex-direction: column">
    <div style="display: flex; justify-content: space-between">
      <div style="width: 400px; float: left">
        <div v-if="cfg.notice">{{ cfg.notice }}</div>
      </div>
    </div>
    <div class="login-container">
      <t-card class="login-card">
        <h2 class="login-title">
          <span class="brand-logo" aria-hidden="true">🐻</span>
          <div v-if="isRegister" style="margin-top: 20px">创建帐户</div>
          <div v-else style="margin-top: 20px">欢迎回来</div>
        </h2>
        <t-loading :loading="loading">
          <t-form :data="loginForm" :label-width="0" :rules="rules" ref="loginFormRef" @submit="onSubmit">
            <t-form-item name="username">
              <t-input v-model="loginForm.username" placeholder="用户名" size="large"></t-input>
            </t-form-item>
            <t-form-item name="password">
              <t-input v-model="loginForm.password" type="password" autocomplete="on" placeholder="密码" size="large"></t-input>
            </t-form-item>

            <t-form-item>
              <t-button theme="success" type="submit" size="large" class="login-button">
                <span v-if="isRegister">注册</span>
                <span v-else>登录</span>
              </t-button>
            </t-form-item>
          </t-form>
        </t-loading>
        <div style="text-align: center; margin-top: 15px">
          <div v-if="isRegister">
            已经拥有帐户？<t-link :underline="false" href="#/login" style="color: #10a37f">登录</t-link> or
            <t-link :underline="false" style="color: red" @click="goFree">免费体验</t-link>
          </div>
          <div v-else>
            没有帐户？
            <t-link :underline="false" href="#/register" style="color: #10a37f">注册</t-link> or
            <t-link :underline="false" style="color: red" @click="goFree">免费体验</t-link>
          </div>
        </div>
        <div class="creator-signature">制作者:Xiaoxiong</div>
      </t-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { MessagePlugin } from 'tdesign-vue-next'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()
const loading = ref(false)
const route = useRoute()
const router = useRouter()
const cfg = ref({ show_github: true, notice: '' })
const loginFormRef = ref()

const loginForm = reactive({
  username: '',
  password: ''
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

const isRegister = computed(() => {
  return route.path.endsWith('/register')
})

onMounted(async () => {
  if (route.query.logout === '1') {
    userStore.logout()
  }
  await getVersionCfg()
})

const getVersionCfg = async () => {
  try {
    const response = await fetch('/0x/user/version-cfg')
    const data = await response.json()
    Object.assign(cfg.value, data)
  } catch (e) {
    console.error('Failed to get version config')
  }
}

const onSubmit = async ({ validateResult }: any) => {
  if (validateResult === true) {
    loading.value = true
    try {
      const url = isRegister.value ? '/0x/user/register' : '/0x/user/login'
      const data = await userStore.login(url, loginForm)
      
      if (data.admin_token && data.is_admin) {
        router.push({ name: 'User' })
      } else if (data.admin_token) {
        router.push({ name: 'LoginChatgpt' })
      }
    } catch (error: any) {
      MessagePlugin.error(error.message || '操作失败')
    }
    loading.value = false
  }
}

const goFree = async () => {
  loading.value = true
  try {
    const data = await userStore.login('/0x/user/login-free', {})
    if (data.admin_token) {
      router.push({ name: 'LoginChatgpt' })
    }
  } catch (error: any) {
    MessagePlugin.error(error.message || '免费体验暂不可用')
  }
  loading.value = false
}
</script>

<style scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 80vh;
}

.login-card {
  width: 400px;
  padding: 20px;
}

.login-title {
  text-align: center;
  margin-bottom: 30px;
  color: #333;
}

.brand-logo {
  display: inline-flex;
  width: 48px;
  height: 48px;
  align-items: center;
  justify-content: center;
  font-size: 44px;
  line-height: 1;
}

.login-button {
  width: 100%;
}

.creator-signature {
  margin-top: 18px;
  text-align: center;
  color: #6b7280;
  font-size: 12px;
}
</style>

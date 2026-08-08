import { createRouter, createWebHashHistory, RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/store/user'

function hasChatGPTSession(): boolean {
  return false
}

function clearAccessibleCookies(): void {
  const cookies = document.cookie.split(';')
  for (const entry of cookies) {
    const [rawName] = entry.split('=', 1)
    const name = rawName?.trim()
    if (!name) continue
    document.cookie = `${name}=; Path=/; Max-Age=0`
  }
}

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/login'
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/pages/login/index.vue')
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/pages/login/index.vue')
  },
  {
    path: '/login-chatgpt',
    name: 'LoginChatgpt',
    component: () => import('@/pages/login/chatgpt.vue')
  },
  {
    path: '/account',
    name: 'Account',
    component: () => import('@/layouts/index.vue'),
    redirect: '/account/overview',
    children: [
      {
        path: 'overview',
        name: 'Overview',
        component: () => import('@/pages/account/overview.vue'),
        meta: { title: '运维概览', requiresAdmin: true }
      },
      {
        path: 'user',
        name: 'User',
        component: () => import('@/pages/account/user.vue'),
        meta: { title: '用户', requiresAdmin: true }
      },
      {
        path: 'chatgpt',
        name: 'ChatGPT',
        component: () => import('@/pages/account/chatgpt.vue'),
        meta: { title: '上游账号', requiresAdmin: true }
      },
      {
        path: 'gptcar',
        name: 'GptCar',
        component: () => import('@/pages/account/gptcar.vue'),
        meta: { title: '账号池', requiresAdmin: true }
      },
      {
        path: 'logs',
        name: 'Logs',
        component: () => import('@/pages/account/logs.vue'),
        meta: { title: '日志', requiresAdmin: true }
      },
      {
        path: 'proxy',
        name: 'Proxy',
        component: () => import('@/pages/account/proxy.vue'),
        meta: { title: '代理', requiresAdmin: true }
      },
      {
        path: 'scripts',
        name: 'Scripts',
        component: () => import('@/pages/account/scripts.vue'),
        meta: { title: '脚本', requiresAdmin: true }
      },
      {
        path: 'access',
        name: 'AccessControl',
        component: () => import('@/pages/account/access.vue'),
        meta: { title: '访问与安全', requiresAdmin: true }
      },
      {
        path: 'profile',
        name: 'Profile',
        component: () => import('@/pages/account/profile.vue'),
        meta: { title: '账户中心' }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHashHistory('/admin/'),
  routes
})

// 路由守卫
router.beforeEach(async (to, _from, next) => {
  const userStore = useUserStore()
  const isLoginPage = to.path === '/login' || to.path === '/login-chatgpt'

  if (isLoginPage && hasChatGPTSession()) {
    window.location.replace('/chat')
    next(false)
    return
  }

  const authenticated = await userStore.hydrate()
  if (to.meta.requiresAdmin && (!authenticated || !userStore.isAdmin)) {
    clearAccessibleCookies()
    window.location.replace('/admin#/')
    next(false)
    return
  }
  
  if (to.path !== '/login' && to.path !== '/register' && !authenticated) {
    next('/login')
  } else {
    next()
  }
})

export default router

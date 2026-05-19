import { createRouter, createWebHashHistory, RouteRecordRaw } from 'vue-router'

function getCookie(name: string): string {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : ''
}

function hasChatGPTSession(): boolean {
  return getCookie('chatgpt_username') !== ''
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
    redirect: '/account/user',
    children: [
      {
        path: 'user',
        name: 'User',
        component: () => import('@/pages/account/user.vue'),
        meta: { title: '用户管理', requiresAdmin: true }
      },
      {
        path: 'chatgpt',
        name: 'ChatGPT',
        component: () => import('@/pages/account/chatgpt.vue'),
        meta: { title: 'ChatGPT账号', requiresAdmin: true }
      },
      {
        path: 'gptcar',
        name: 'GptCar',
        component: () => import('@/pages/account/gptcar.vue'),
        meta: { title: '号池管理', requiresAdmin: true }
      },
      {
        path: 'logs',
        name: 'Logs',
        component: () => import('@/pages/account/logs.vue'),
        meta: { title: '访问日志', requiresAdmin: true }
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
      }
    ]
  }
]

const router = createRouter({
  history: createWebHashHistory('/admin/'),
  routes
})

// 路由守卫
router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('admin_token')
  const isAdmin = localStorage.getItem('is_admin') === 'true'
  const isLoginPage = to.path === '/login' || to.path === '/login-chatgpt'

  if (isLoginPage && hasChatGPTSession()) {
    window.location.replace('/chat')
    next(false)
    return
  }

  if (to.meta.requiresAdmin && (!token || !isAdmin)) {
    clearAccessibleCookies()
    localStorage.removeItem('admin_token')
    localStorage.removeItem('is_admin')
    localStorage.removeItem('username')
    window.location.replace('/admin#/')
    next(false)
    return
  }
  
  if (to.path !== '/login' && to.path !== '/register' && !token) {
    next('/login')
  } else {
    next()
  }
})

export default router
